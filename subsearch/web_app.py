import os
import json
import logging
import threading
import tempfile
import time
import re
import smtplib
import ssl
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage

from flask import Flask, render_template, request, send_file, flash, redirect, url_for, session, make_response, jsonify
from dotenv import load_dotenv

# Reuse core analyzer functions
from .auto_sub_analyzer import find_unmoderated_subreddits, save_to_csv
from .build_info import get_current_build_number
from .storage import (
    fetch_recent_runs,
    get_summary_stats,
    get_node_stats,
    get_config_warnings,
    list_public_nodes,
    init_db,
    create_volunteer_node,
    get_node_by_token,
    update_volunteer_node,
    delete_volunteer_node,
    mark_manage_link_sent,
    prune_broken_nodes,
    persist_subreddits,
    record_run_complete,
    record_run_start,
    search_subreddits,
)

import praw
import prawcore


load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")

# Logging setup
log_level = logging.DEBUG if os.getenv("FLASK_DEBUG") == "1" or os.getenv("DEBUG") == "1" else logging.INFO
logging.basicConfig(level=log_level, format='[%(asctime)s] %(levelname)s in %(name)s: %(message)s')
logger = logging.getLogger("web_app")

# Job store for background runs
jobs = {}
jobs_lock = threading.Lock()
auto_ingest_thread = None
auto_ingest_lock = threading.Lock()
node_cleanup_thread = None
node_cleanup_lock = threading.Lock()

# Restrict directory browsing removed (no server-side saving)
SITE_URL = os.getenv("SITE_URL", "")

NODE_EMAIL_SENDER = os.getenv("NODE_EMAIL_SENDER", "").strip()
NODE_EMAIL_SENDER_NAME = os.getenv("NODE_EMAIL_SENDER_NAME", "Sub Search Nodes").strip() or "Sub Search Nodes"
NODE_EMAIL_SMTP_HOST = os.getenv("NODE_EMAIL_SMTP_HOST", "").strip()
try:
    NODE_EMAIL_SMTP_PORT = int(os.getenv("NODE_EMAIL_SMTP_PORT", "587") or 587)
except (TypeError, ValueError):
    NODE_EMAIL_SMTP_PORT = 587
NODE_EMAIL_SMTP_USERNAME = os.getenv("NODE_EMAIL_SMTP_USERNAME", "").strip()
NODE_EMAIL_SMTP_PASSWORD = os.getenv("NODE_EMAIL_SMTP_PASSWORD", "").strip()
NODE_EMAIL_USE_TLS = str(os.getenv("NODE_EMAIL_USE_TLS", "1")).strip().lower() not in {"0", "false", "off", "no"}
try:
    NODE_CLEANUP_INTERVAL_SECONDS = int(os.getenv("NODE_CLEANUP_INTERVAL_SECONDS", "86400") or 86400)
except (TypeError, ValueError):
    NODE_CLEANUP_INTERVAL_SECONDS = 86400
NODE_CLEANUP_INTERVAL_SECONDS = max(3600, NODE_CLEANUP_INTERVAL_SECONDS)
try:
    NODE_BROKEN_RETENTION_DAYS = int(os.getenv("NODE_BROKEN_RETENTION_DAYS", "7") or 7)
except (TypeError, ValueError):
    NODE_BROKEN_RETENTION_DAYS = 7
NODE_BROKEN_RETENTION_DAYS = max(1, NODE_BROKEN_RETENTION_DAYS)

@app.route("/")
def home():
    stats = get_summary_stats() or {}
    stats_display = dict(stats)
    stats_display["last_indexed_display"] = _format_human_ts(stats.get("last_indexed"))
    stats_display["last_run_display"] = _format_human_ts(stats.get("last_run_started"))
    recent_runs = fetch_recent_runs(limit=5)
    for run in recent_runs:
        run["started_display"] = _format_human_ts(run.get("started_at"))
        if run.get("error"):
            run["status"] = "error"
        elif run.get("completed_at"):
            run["status"] = "complete"
        else:
            run["status"] = "running"
    node_stats = get_node_stats() or {"total": 0, "active": 0, "pending": 0, "broken": 0}
    volunteer_nodes = []
    for entry in list_public_nodes(limit=6):
        item = dict(entry)
        item["last_check_display"] = _format_human_ts(entry.get("last_check_in_at") or entry.get("updated_at"))
        volunteer_nodes.append(item)
    return render_template(
        "home.html",
        stats=stats_display,
        recent_runs=recent_runs,
        node_stats=node_stats,
        volunteer_nodes=volunteer_nodes,
        nav_active="home",
    )


@app.route("/nodes")
def nodes_home():
    stats = get_node_stats() or {"total": 0, "active": 0, "pending": 0, "broken": 0}
    volunteer_nodes = []
    for entry in list_public_nodes(limit=30):
        item = dict(entry)
        item["last_check_display"] = _format_human_ts(entry.get("last_check_in_at") or entry.get("updated_at"))
        volunteer_nodes.append(item)
    return render_template(
        "nodes/index.html",
        node_stats=stats,
        volunteer_nodes=volunteer_nodes,
        nav_active="nodes",
    )


@app.route("/nodes/join", methods=["GET", "POST"])
def node_join():
    form_data = {
        "email": (request.form.get("email") or "").strip(),
        "reddit_username": _normalize_username(request.form.get("reddit_username") or ""),
        "location": (request.form.get("location") or "").strip(),
        "system_details": (request.form.get("system_details") or "").strip(),
        "availability": (request.form.get("availability") or "").strip(),
        "bandwidth_notes": (request.form.get("bandwidth_notes") or "").strip(),
        "notes": (request.form.get("notes") or "").strip(),
    }
    manage_link = None
    email_sent = False
    if request.method == "POST":
        errors = []
        if not form_data["email"] or "@" not in form_data["email"]:
            errors.append("A valid contact email is required.")
        if not form_data["reddit_username"]:
            errors.append("Share the Reddit account you plan to run with.")
        if errors:
            for err in errors:
                flash(err, "error")
        else:
            token = create_volunteer_node(
                email=form_data["email"],
                reddit_username=form_data["reddit_username"],
                location=form_data["location"],
                system_details=form_data["system_details"],
                availability=form_data["availability"],
                bandwidth_notes=form_data["bandwidth_notes"],
                notes=form_data["notes"],
            )
            manage_link = _build_manage_link(token)
            email_sent = _send_node_email(form_data["email"], manage_link)
            if email_sent:
                mark_manage_link_sent(token)
                flash(
                    "Thanks for volunteering! Check your inbox for the private link to manage your node.",
                    "success",
                )
            else:
                flash(
                    "Thanks for volunteering! Email delivery isn't configured, so copy the private link below to manage your node.",
                    "warning",
                )
            form_data = {key: "" for key in form_data}
    return render_template(
        "nodes/join.html",
        form_data=form_data,
        manage_link=manage_link,
        email_sent=email_sent,
        nav_active="nodes",
    )


@app.route("/nodes/manage/<token>", methods=["GET", "POST"])
def node_manage(token):
    node = get_node_by_token(token)
    if not node:
        flash("That node link is no longer active. Submit the join form again for a fresh link.", "error")
        return redirect(url_for("node_join"))
    if request.method == "POST":
        action = request.form.get("action")
        if action == "delete":
            delete_volunteer_node(token)
            flash("Your node has been removed. Thanks for contributing!", "success")
            return redirect(url_for("nodes_home"))
        updated_email = (request.form.get("email") or "").strip()
        updated_username = _normalize_username(request.form.get("reddit_username") or "")
        updated_location = (request.form.get("location") or "").strip()
        updated_system = (request.form.get("system_details") or "").strip()
        updated_availability = (request.form.get("availability") or "").strip()
        updated_bandwidth = (request.form.get("bandwidth_notes") or "").strip()
        updated_notes = (request.form.get("notes") or "").strip()
        chosen_status = request.form.get("health_status") or node.get("health_status") or "active"
        node["email"] = updated_email
        node["reddit_username"] = updated_username
        node["location"] = updated_location
        node["system_details"] = updated_system
        node["availability"] = updated_availability
        node["bandwidth_notes"] = updated_bandwidth
        node["notes"] = updated_notes
        node["health_status"] = chosen_status
        errors = []
        if not updated_email or "@" not in updated_email:
            errors.append("Email is required so we can keep your node reachable.")
        if not updated_username:
            errors.append("Your Reddit username helps coordinate API access.")
        if errors:
            for err in errors:
                flash(err, "error")
        else:
            broken_since = None
            previous_status = (node.get("health_status") or "").lower()
            if chosen_status == "broken" and (previous_status != "broken" or not node.get("broken_since")):
                broken_since = datetime.utcnow().isoformat()
            elif previous_status == "broken" and chosen_status != "broken":
                broken_since = ""
            updated = update_volunteer_node(
                token,
                email=updated_email,
                reddit_username=updated_username,
                location=updated_location,
                system_details=updated_system,
                availability=updated_availability,
                bandwidth_notes=updated_bandwidth,
                notes=updated_notes,
                health_status=chosen_status,
                broken_since=broken_since,
            )
            if updated:
                flash("Node details updated.", "success")
                return redirect(url_for("node_manage", token=token))
            flash("No changes detected.", "info")
    manage_link = _build_manage_link(token)
    last_check_display = _format_human_ts(
        node.get("last_check_in_at") or node.get("updated_at") or node.get("created_at")
    )
    return render_template(
        "nodes/manage.html",
        node=node,
        manage_link=manage_link,
        last_check_display=last_check_display,
        nav_active="nodes",
    )


@app.context_processor
def inject_globals():
    return {
        "site_url": SITE_URL,
        "datetime": datetime,
        "build_number": get_current_build_number(),
        "config_warnings": get_config_warnings(),
    }


def default_output_filename():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"unmoderated_subreddits_{timestamp}.csv"


def _safe_int(value, default=None):
    if value is None:
        return default
    if isinstance(value, int):
        return value
    try:
        cleaned = str(value).replace(",", "").strip()
        if cleaned == "":
            return default
        return int(cleaned)
    except (TypeError, ValueError):
        return default


def _parse_bool_flag(value):
    if value is None or value == "":
        return None
    val = str(value).strip().lower()
    if val in ("1", "true", "yes", "y", "on"):
        return True
    if val in ("0", "false", "no", "n", "off"):
        return False
    return None


def _parse_iso(ts):
    if not ts:
        return None
    if isinstance(ts, datetime):
        return ts
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        try:
            if ts.endswith("Z"):
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            return None
    except Exception:
        return None
    return None


def _format_human_ts(ts):
    dt = _parse_iso(ts)
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _normalize_username(value: str) -> str:
    if not value:
        return ""
    cleaned = value.strip()
    lowered = cleaned.lower()
    if lowered.startswith("/u/"):
        cleaned = cleaned[3:]
    elif lowered.startswith("u/"):
        cleaned = cleaned[2:]
    return cleaned.strip().lstrip("/")


def _build_manage_link(token: str) -> str:
    if not token:
        return ""
    path = url_for("node_manage", token=token, _external=False)
    if SITE_URL:
        return f"{SITE_URL.rstrip('/')}{path}"
    return url_for("node_manage", token=token, _external=True)


def _send_node_email(recipient: str, manage_link: str) -> bool:
    if not recipient or not manage_link:
        return False
    if not NODE_EMAIL_SENDER or not NODE_EMAIL_SMTP_HOST:
        logger.warning("Node email not sent because SMTP settings are incomplete.")
        return False
    message = EmailMessage()
    sender = NODE_EMAIL_SENDER
    if NODE_EMAIL_SENDER_NAME:
        sender = f"{NODE_EMAIL_SENDER_NAME} <{NODE_EMAIL_SENDER}>"
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = "Your Sub Search volunteer node link"
    message.set_content(
        (
            "Thanks for offering your machine to help grow the Sub Search dataset!\n\n"
            "Here is your private link to manage your node:\n"
            f"{manage_link}\n\n"
            "Use it to update hardware details, pause contributions, or delete the node entirely.\n"
            "We keep nodes that report a broken state for 7+ days automatically cleared out each night.\n\n"
            "- Sub Search"
        )
    )
    try:
        with smtplib.SMTP(NODE_EMAIL_SMTP_HOST, NODE_EMAIL_SMTP_PORT, timeout=20) as smtp:
            if NODE_EMAIL_USE_TLS:
                context = ssl.create_default_context()
                smtp.starttls(context=context)
            if NODE_EMAIL_SMTP_USERNAME:
                smtp.login(NODE_EMAIL_SMTP_USERNAME, NODE_EMAIL_SMTP_PASSWORD)
            smtp.send_message(message)
        logger.info("Sent volunteer node link to %s", recipient)
        return True
    except Exception:
        logger.exception("Unable to send volunteer node email to %s", recipient)
        return False


AUTO_INGEST_ENABLED = str(os.getenv("AUTO_INGEST_ENABLED", "1")).strip().lower() not in {"0", "false", "off", "no"}
AUTO_INGEST_INTERVAL_MINUTES = max(15, _safe_int(os.getenv("AUTO_INGEST_INTERVAL_MINUTES"), 180) or 180)
AUTO_INGEST_LIMIT = min(5000, max(100, _safe_int(os.getenv("AUTO_INGEST_LIMIT"), 1000) or 1000))
AUTO_INGEST_MIN_SUBS = max(0, _safe_int(os.getenv("AUTO_INGEST_MIN_SUBS"), 0) or 0)
try:
    AUTO_INGEST_DELAY = max(0.0, float(os.getenv("AUTO_INGEST_DELAY_SEC", "0.25") or 0.25))
except ValueError:
    AUTO_INGEST_DELAY = 0.25
AUTO_INGEST_KEYWORDS = [k.strip() for k in os.getenv("AUTO_INGEST_KEYWORDS", "").split(",") if k.strip()]


def _run_auto_ingest_job(keyword=None):
    import uuid

    job_id = uuid.uuid4().hex
    label_raw = keyword or "global"
    label = re.sub(r"[^A-Za-z0-9]+", "-", label_raw).strip("-").lower() or "global"
    job_params = {
        'keyword': keyword,
        'limit': AUTO_INGEST_LIMIT,
        'unmoderated_only': False,
        'exclude_nsfw': False,
        'min_subs': AUTO_INGEST_MIN_SUBS,
        'activity_mode': "any",
        'activity_threshold_utc': None,
        'file_name': f"auto_ingest_{label}_{datetime.now().strftime('%Y%m%d')}.csv",
    }
    record_run_start(job_id, job_params, source="auto-ingest")
    subs = []
    try:
        subs = find_unmoderated_subreddits(
            limit=AUTO_INGEST_LIMIT,
            name_keyword=keyword,
            unmoderated_only=False,
            exclude_nsfw=False,
            min_subscribers=AUTO_INGEST_MIN_SUBS,
            activity_mode="any",
            activity_threshold_utc=None,
            progress_callback=None,
            stop_callback=None,
            rate_limit_delay=AUTO_INGEST_DELAY,
        )
        persist_subreddits(job_id, subs, keyword=keyword, source="auto-ingest")
        record_run_complete(job_id, len(subs), error=None)
        logger.info("Auto-ingest job %s (%s) stored %d subreddits", job_id, label, len(subs))
    except Exception as exc:
        record_run_complete(job_id, len(subs), error=str(exc))
        logger.exception("Auto-ingest job %s (%s) failed: %s", job_id, label, exc)


def _auto_ingest_loop():
    keywords = AUTO_INGEST_KEYWORDS or [None]
    interval_seconds = AUTO_INGEST_INTERVAL_MINUTES * 60
    logger.info(
        "Auto-ingest loop active (interval=%d min, limit=%d, keywords=%s)",
        AUTO_INGEST_INTERVAL_MINUTES,
        AUTO_INGEST_LIMIT,
        keywords,
    )
    while True:
        for keyword in keywords:
            if not AUTO_INGEST_ENABLED:
                logger.info("Auto-ingest disabled at runtime, stopping loop.")
                return
            _run_auto_ingest_job(keyword or None)
        time.sleep(interval_seconds)


def _start_auto_ingest_thread_if_needed():
    global auto_ingest_thread
    if not AUTO_INGEST_ENABLED:
        logger.info("Auto-ingest disabled (AUTO_INGEST_ENABLED=0).")
        return
    with auto_ingest_lock:
        if auto_ingest_thread and auto_ingest_thread.is_alive():
            return
        auto_ingest_thread = threading.Thread(target=_auto_ingest_loop, name="auto-ingest", daemon=True)
        auto_ingest_thread.start()


def _node_cleanup_loop():
    while True:
        try:
            removed = prune_broken_nodes(NODE_BROKEN_RETENTION_DAYS)
            if removed:
                logger.info(
                    "Nightly node cleanup removed %d broken node(s) older than %d days",
                    removed,
                    NODE_BROKEN_RETENTION_DAYS,
                )
        except Exception:
            logger.exception("Nightly node cleanup failed.")
        time.sleep(NODE_CLEANUP_INTERVAL_SECONDS)


def _start_node_cleanup_thread_if_needed():
    global node_cleanup_thread
    with node_cleanup_lock:
        if node_cleanup_thread and node_cleanup_thread.is_alive():
            return
        node_cleanup_thread = threading.Thread(target=_node_cleanup_loop, name="node-cleanup", daemon=True)
        node_cleanup_thread.start()


# Prepare storage and background ingestion
init_db()
_start_auto_ingest_thread_if_needed()
_start_node_cleanup_thread_if_needed()


@app.route("/analyzer", methods=["GET", "POST"])
def analyzer():
    result = None
    job_id = request.args.get("job")

    if request.method == "POST":
        # Read raw inputs
        keyword_raw = request.form.get("keyword", "").strip()
        limit_raw = request.form.get("limit", "1000").strip()
        file_name_raw = request.form.get("file_name", "").strip()
        unmoderated_only = request.form.get("unmoderated_only") == "on"
        exclude_nsfw = request.form.get("exclude_nsfw") == "on"
        min_subs_raw = request.form.get("min_subs", "100").strip()
        activity_enabled = request.form.get("activity_enabled") == "on"
        activity_mode = request.form.get("activity_mode", "any").strip()
        activity_date_raw = request.form.get("activity_date", "").strip()

        # Server-side validation and sanitization
        def sanitize_keyword(s: str) -> str:
            s = s[:64]
            return re.sub(r"[^A-Za-z0-9 _\-]", "", s)

        def sanitize_filename(name: str) -> str:
            name = name.strip()[:64]
            # Disallow path separators and parent traversals
            if "/" in name or "\\" in name or name in (".", ".."):
                return ""
            # Whitelist chars
            name = re.sub(r"[^A-Za-z0-9._\-]", "", name)
            return name

        # Accept commas in numeric fields
        limit_raw_clean = limit_raw.replace(",", "").replace("_", "").replace(" ", "")
        try:
            limit = int(limit_raw_clean)
            if limit <= 0 or limit > 100000:
                raise ValueError
        except ValueError:
            flash("Limit must be an integer between 1 and 100,000.", "error")
            return render_template("index.html", result=None, job_id=None, site_url=SITE_URL, nav_active="analyzer")

        keyword = sanitize_keyword(keyword_raw) or None

        file_name = sanitize_filename(file_name_raw)
        if not file_name:
            file_name = default_output_filename()
        # Ensure csv extension
        if not file_name.lower().endswith(".csv"):
            file_name += ".csv"

        # Minimum subscribers
        min_subs_raw_clean = min_subs_raw.replace(",", "").replace("_", "").replace(" ", "")
        try:
            min_subs = int(min_subs_raw_clean)
            if min_subs < 0 or min_subs > 10_000_000:
                raise ValueError
        except ValueError:
            flash("Minimum subscribers must be a non-negative integer.", "error")
            return render_template("index.html", result=None, job_id=None, site_url=SITE_URL, nav_active="analyzer")

        # Activity date filter
        activity_threshold_utc = None
        if activity_enabled and activity_mode in ("active_after", "inactive_before") and activity_date_raw:
            # Expect YYYY-MM-DD
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", activity_date_raw):
                flash("Invalid date format. Use YYYY-MM-DD.", "error")
                return render_template("index.html", result=None, job_id=None, site_url=SITE_URL, nav_active="analyzer")
            try:
                dt = datetime.strptime(activity_date_raw, "%Y-%m-%d")
                activity_threshold_utc = int(dt.timestamp())
            except Exception:
                flash("Invalid date provided.", "error")
                return render_template("index.html", result=None, job_id=None, site_url=SITE_URL, nav_active="analyzer")
        elif not activity_enabled:
            activity_mode = "any"
            activity_date_raw = ""

        def progress(checked, found):
            with jobs_lock:
                if job_id in jobs:
                    jobs[job_id]['checked'] = checked
                    jobs[job_id]['found'] = found

        # Create job record
        import uuid
        job_params = {
            'keyword': keyword,
            'limit': limit,
            'unmoderated_only': unmoderated_only,
            'exclude_nsfw': exclude_nsfw,
            'min_subs': min_subs,
            'activity_mode': activity_mode,
            'activity_threshold_utc': activity_threshold_utc,
            'file_name': file_name,
        }
        job_id = uuid.uuid4().hex
        with jobs_lock:
            jobs[job_id] = {
                'keyword': keyword,
                'limit': limit,
                'unmoderated_only': unmoderated_only,
                'exclude_nsfw': exclude_nsfw,
                'min_subs': min_subs,
                'activity_mode': activity_mode,
                'activity_date': activity_date_raw,
                'checked': 0,
                'found': 0,
                'done': False,
                'error': None,
                'output_path': None,
                'file_name': file_name,
                'started_at': datetime.now(timezone.utc).isoformat(),
                'stopped': False,
                'stop': False,
                'source': 'analyzer',
            }
        record_run_start(job_id, job_params, source="analyzer")

        def run_job():
            logger.info(f"Job {job_id} started: keyword=%r limit=%d unmoderated_only=%s output_dir=%r file_name=%r",
                        keyword, limit, unmoderated_only, None, file_name)
            subs = []
            try:
                subs = find_unmoderated_subreddits(
                    limit=limit,
                    name_keyword=keyword,
                    unmoderated_only=unmoderated_only,
                    exclude_nsfw=exclude_nsfw,
                    min_subscribers=min_subs,
                    activity_mode=activity_mode,
                    activity_threshold_utc=activity_threshold_utc,
                    progress_callback=progress,
                    stop_callback=lambda: jobs.get(job_id, {}).get('stop', False),
                )
                # Always save to a temp dir for download only.
                tmp_dir = tempfile.mkdtemp(prefix="sub_an_")
                output_path = os.path.join(tmp_dir, file_name)
                save_to_csv(subs, filename=output_path)
                try:
                    persist_subreddits(job_id, subs, keyword=keyword, source="analyzer")
                except Exception:
                    logger.exception("Failed to persist subreddits for job %s", job_id)
                with jobs_lock:
                    jobs[job_id]['done'] = True
                    jobs[job_id]['output_path'] = os.path.abspath(output_path)
                    jobs[job_id]['found'] = len(subs)
                    if jobs[job_id].get('stop'):
                        jobs[job_id]['stopped'] = True
                record_run_complete(job_id, len(subs), error=None)
                logger.info(f"Job {job_id} finished: saved to %s (found=%d)", output_path, len(subs))
            except Exception as e:
                logger.exception("Job %s errored", job_id)
                with jobs_lock:
                    jobs[job_id]['error'] = str(e)
                    jobs[job_id]['done'] = True
                record_run_complete(job_id, len(subs), error=str(e))

        t = threading.Thread(target=run_job, daemon=True)
        t.start()
        # Redirect to page with job param so client can poll
        return redirect(url_for('analyzer', job=job_id))

    return render_template("index.html", result=result, job_id=job_id, site_url=SITE_URL, nav_active="analyzer")


@app.route("/all-the-subs")
def all_subs():
    initial_filters = {
        "q": request.args.get("q", "").strip(),
        "min_subs": request.args.get("min_subs", "").strip(),
        "unmoderated": request.args.get("unmoderated", "").strip(),
        "nsfw": request.args.get("nsfw", "").strip(),
        "sort": request.args.get("sort", "subscribers").strip() or "subscribers",
        "order": request.args.get("order", "desc").strip() or "desc",
    }
    return render_template(
        "all_subs.html",
        initial_filters=initial_filters,
        nav_active="allsubs",
    )


@app.route("/download")
def download():
    # Safer download: require a known job id or session path
    job_id = request.args.get("job")
    path = None
    if job_id:
        with jobs_lock:
            job = jobs.get(job_id)
            if job and job.get('done'):
                path = job.get('output_path')
    if not path:
        # Fallback to provided path only if it matches any known job output
        qpath = request.args.get("path")
        if qpath:
            with jobs_lock:
                for j in jobs.values():
                    if j.get('output_path') == qpath:
                        path = qpath
                        break
    if not path:
        flash("No authorized file available for download.", "error")
        return redirect(url_for("analyzer"))
    if not os.path.exists(path):
        flash("File not found for download.", "error")
        return redirect(url_for("analyzer"))
    return send_file(path, as_attachment=True, conditional=True)


@app.route('/favicon.ico')
def favicon():
    # Tiny inline SVG served as .ico response to avoid 404s
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
        "<defs><radialGradient id='g' cx='50%' cy='50%' r='60%'>"
        "<stop offset='0%' stop-color='#22d3ee'/><stop offset='100%' stop-color='#7c3aed'/></radialGradient></defs>"
        "<rect width='64' height='64' rx='14' fill='url(#g)'/>"
        "<circle cx='32' cy='32' r='10' fill='white' opacity='0.9'/></svg>"
    )
    resp = make_response(svg)
    resp.headers['Content-Type'] = 'image/svg+xml'
    return resp


@app.route('/status/<job_id>')
def status(job_id):
    with jobs_lock:
        data = jobs.get(job_id)
        if not data:
            return jsonify({"error": "unknown job"}), 404
        # Do not leak full server paths unless job done
        safe = dict(data)
        return jsonify(safe)


@app.post('/stop/<job_id>')
def stop(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify({"ok": False, "error": "unknown job"}), 404
        if job.get('done'):
            return jsonify({"ok": False, "error": "already done"}), 400
        job['stop'] = True
    logger.info("Stop requested for job %s", job_id)
    return jsonify({"ok": True})


@app.route('/helpdocs')
def helpdocs():
    # Redirect to GitHub help docs section
    return redirect('https://github.com/ericrosenberg1/reddit-sub-analyzer#helpdocs', code=302)


@app.get("/api/subreddits")
def api_subreddits():
    q = request.args.get("q", "").strip()
    is_unmoderated = _parse_bool_flag(request.args.get("unmoderated"))
    nsfw = _parse_bool_flag(request.args.get("nsfw"))
    min_subs = _safe_int(request.args.get("min_subs"))
    max_subs = _safe_int(request.args.get("max_subs"))
    page = _safe_int(request.args.get("page"), 1) or 1
    page_size = _safe_int(request.args.get("page_size"), 50) or 50
    sort = request.args.get("sort", "subscribers")
    order = request.args.get("order", "desc")

    data = search_subreddits(
        q=q or None,
        is_unmoderated=is_unmoderated,
        nsfw=nsfw,
        min_subs=min_subs,
        max_subs=max_subs,
        sort=sort or "subscribers",
        order=order or "desc",
        page=page,
        page_size=page_size,
    )
    return jsonify(data)


def run():
    # Run on a non-standard port for easy access
    port = int(os.getenv("PORT", "5055"))
    # Elevate logging when running in debug mode
    logger.setLevel(logging.DEBUG)
    logging.getLogger("analyzer").setLevel(logging.DEBUG)
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    run()
