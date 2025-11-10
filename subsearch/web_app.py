import os
import json
import logging
import threading
import time
import re
import smtplib
import ssl
import csv
import io
from collections import deque
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage

from flask import Flask, render_template, request, flash, redirect, url_for, session, make_response, jsonify, Response
from dotenv import load_dotenv

# Reuse core analyzer functions
from .auto_sub_analyzer import find_unmoderated_subreddits
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
    fetch_subreddits_by_job,
    get_run_id_by_job,
    get_job_filters,
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
job_queue = deque()
queue_lock = threading.Lock()
running_jobs = set()
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


MAX_CONCURRENT_JOBS = max(1, _safe_int(os.getenv("SUBSEARCH_MAX_CONCURRENT_JOBS"), 1) or 1)
try:
    RATE_LIMIT_DELAY = float(os.getenv("SUBSEARCH_RATE_LIMIT_DELAY", "0.2") or 0.2)
except (TypeError, ValueError):
    RATE_LIMIT_DELAY = 0.2
RATE_LIMIT_DELAY = max(0.1, RATE_LIMIT_DELAY)


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
    }
    record_run_start(job_id, job_params, source="auto-ingest")
    subs = []
    try:
        result = find_unmoderated_subreddits(
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
            include_all=True,
        )
        filtered = result.get("results", [])
        evaluated = result.get("evaluated", filtered)
        persist_subreddits(job_id, evaluated, keyword=keyword, source="auto-ingest")
        record_run_complete(job_id, len(filtered), error=None)
        logger.info(
            "Auto-ingest job %s (%s) stored %d evaluated subs (%d matched filters)",
            job_id,
            label,
            len(evaluated),
            len(filtered),
        )
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


def _update_queue_positions_locked():
    queue_len = len(job_queue)
    return [(job_id, idx, queue_len) for idx, job_id in enumerate(list(job_queue))]


def _apply_queue_positions(updates):
    if not updates:
        return
    with jobs_lock:
        for job_id, idx, queue_len in updates:
            job = jobs.get(job_id)
            if not job:
                continue
            job["queue_position"] = idx + 1
            job["orders_ahead"] = idx
            job["queue_size"] = queue_len


def _enqueue_job(job_id: str) -> None:
    with queue_lock:
        job_queue.append(job_id)
        updates = _update_queue_positions_locked()
    _apply_queue_positions(updates)
    with jobs_lock:
        job = jobs.get(job_id)
        if job:
            job["state"] = "queued"
            job["results_ready"] = False
    _start_jobs_if_possible()


def _start_jobs_if_possible():
    to_start = []
    with queue_lock:
        while len(running_jobs) < MAX_CONCURRENT_JOBS and job_queue:
            job_id = job_queue.popleft()
            running_jobs.add(job_id)
            to_start.append(job_id)
        updates = _update_queue_positions_locked()
    _apply_queue_positions(updates)
    for job_id in to_start:
        with jobs_lock:
            job = jobs.get(job_id)
            if not job:
                with queue_lock:
                    running_jobs.discard(job_id)
                continue
            job["state"] = "running"
            job["queue_position"] = None
            job["orders_ahead"] = None
            job["queue_size"] = len(job_queue)
            job["started_at"] = datetime.now(timezone.utc).isoformat()
        thread = threading.Thread(target=_run_job_thread, args=(job_id,), daemon=True)
        with jobs_lock:
            jobs[job_id]["thread"] = thread
        thread.start()


def _update_job_progress(job_id: str, checked: int, found: int) -> None:
    with jobs_lock:
        job = jobs.get(job_id)
        if job:
            job["checked"] = checked
            job["found"] = found


def _job_should_stop(job_id: str) -> bool:
    with jobs_lock:
        job = jobs.get(job_id)
        return bool(job.get("stop")) if job else True


def _apply_job_filters_to_rows(rows, job_config):
    if not rows or not job_config:
        return rows
    filtered = rows
    if job_config.get("unmoderated_only"):
        filtered = [row for row in filtered if row.get("is_unmoderated")]
    if job_config.get("exclude_nsfw"):
        filtered = [row for row in filtered if not row.get("is_nsfw")]
    min_subs = job_config.get("min_subs")
    if min_subs:
        filtered = [row for row in filtered if (row.get("subscribers") or 0) >= min_subs]
    keyword = (job_config.get("keyword") or "").strip().lower()
    if keyword:
        filtered = [
            row
            for row in filtered
            if keyword in (row.get("name", "").lower())
            or keyword in (row.get("display_name_prefixed", "").lower())
        ]
    mode = job_config.get("activity_mode")
    threshold = job_config.get("activity_threshold_utc")
    if mode in {"active_after", "inactive_before"} and threshold:
        if mode == "active_after":
            filtered = [
                row for row in filtered if row.get("last_activity_utc") and row["last_activity_utc"] >= threshold
            ]
        elif mode == "inactive_before":
            filtered = [
                row
                for row in filtered
                if not row.get("last_activity_utc") or row["last_activity_utc"] < threshold
            ]
    return filtered


def _run_job_thread(job_id: str) -> None:
    job_config = {}
    with jobs_lock:
        job = jobs.get(job_id)
        if job:
            job_config = dict(job.get("job_config") or {})
    if not job_config:
        with queue_lock:
            running_jobs.discard(job_id)
        return

    keyword = job_config.get('keyword')
    limit = job_config.get('limit', 1000)
    unmoderated_only = job_config.get('unmoderated_only', True)
    exclude_nsfw = job_config.get('exclude_nsfw', False)
    min_subs = job_config.get('min_subs', 0)
    activity_mode = job_config.get('activity_mode', "any")
    activity_threshold_utc = job_config.get('activity_threshold_utc')

    logger.info(
        "Job %s started: keyword=%r limit=%d unmoderated_only=%s",
        job_id,
        keyword,
        limit,
        unmoderated_only,
    )

    subs = []
    evaluated = []
    try:
        payload = find_unmoderated_subreddits(
            limit=limit,
            name_keyword=keyword,
            unmoderated_only=unmoderated_only,
            exclude_nsfw=exclude_nsfw,
            min_subscribers=min_subs,
            activity_mode=activity_mode,
            activity_threshold_utc=activity_threshold_utc,
            progress_callback=lambda checked, found: _update_job_progress(job_id, checked, found),
            stop_callback=lambda: _job_should_stop(job_id),
            rate_limit_delay=RATE_LIMIT_DELAY,
            include_all=True,
        )
        subs = payload.get("results", [])
        evaluated = payload.get("evaluated", subs)
        try:
            persist_subreddits(job_id, evaluated, keyword=keyword, source="analyzer")
        except Exception:
            logger.exception("Failed to persist subreddits for job %s", job_id)

        with jobs_lock:
            job = jobs.get(job_id)
            if job:
                job["done"] = True
                job["state"] = "stopped" if job.get("stop") else "complete"
                job["stopped"] = bool(job.get("stop"))
                job["stop"] = False
                job["results_ready"] = True
                job["results"] = subs
                job["found"] = len(subs)
                job["result_count"] = len(subs)
                job["queue_position"] = None
                job["orders_ahead"] = None
                job["queue_size"] = len(job_queue)
        record_run_complete(job_id, len(subs), error=None)
        logger.info("Job %s finished (found=%d)", job_id, len(subs))
    except Exception as e:
        logger.exception("Job %s errored", job_id)
        with jobs_lock:
            job = jobs.get(job_id)
            if job:
                job["error"] = str(e)
                job["done"] = True
                job["state"] = "error"
                job["queue_position"] = None
                job["orders_ahead"] = None
                job["queue_size"] = len(job_queue)
        record_run_complete(job_id, len(subs), error=str(e))
    finally:
        with jobs_lock:
            job = jobs.get(job_id)
            if job:
                job.pop("thread", None)
        with queue_lock:
            running_jobs.discard(job_id)
        _start_jobs_if_possible()


def _remove_from_queue(job_id: str) -> bool:
    removed = False
    with queue_lock:
        try:
            job_queue.remove(job_id)
            removed = True
        except ValueError:
            removed = False
        updates = _update_queue_positions_locked()
    _apply_queue_positions(updates)
    return removed


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
        }
        job_id = uuid.uuid4().hex
        with jobs_lock:
            jobs[job_id] = {
                'job_id': job_id,
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
                'started_at': None,
                'stopped': False,
                'stop': False,
                'source': 'analyzer',
                'state': 'queued',
                'queue_position': None,
                'orders_ahead': None,
                'queue_size': 0,
                'results_ready': False,
                'results': [],
                'result_count': 0,
                'job_config': job_params,
            }
        record_run_start(job_id, job_params, source="analyzer")
        _enqueue_job(job_id)
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
        "job_id": request.args.get("job_id", "").strip(),
    }
    if initial_filters["job_id"]:
        job_filter_defaults = get_job_filters(initial_filters["job_id"])
        if job_filter_defaults:
            if not initial_filters["q"] and job_filter_defaults.get("keyword"):
                initial_filters["q"] = job_filter_defaults["keyword"]
            if not initial_filters["min_subs"] and job_filter_defaults.get("min_subs"):
                initial_filters["min_subs"] = str(job_filter_defaults["min_subs"])
            if not initial_filters["unmoderated"] and job_filter_defaults.get("unmoderated_only"):
                initial_filters["unmoderated"] = "true"
            if not initial_filters["nsfw"] and job_filter_defaults.get("exclude_nsfw"):
                initial_filters["nsfw"] = "false"
    return render_template(
        "all_subs.html",
        initial_filters=initial_filters,
        nav_active="allsubs",
    )


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
    safe = dict(data)
    safe.pop('job_config', None)
    safe.pop('thread', None)
    if not safe.get("results_ready"):
        safe.pop("results", None)
    with queue_lock:
        safe["queue_backlog"] = len(job_queue)
    safe["max_concurrent"] = MAX_CONCURRENT_JOBS
    safe["rate_limit_delay"] = RATE_LIMIT_DELAY
    return jsonify(safe)


@app.route("/job/<job_id>/download.csv")
def job_download_csv(job_id):
    rows = None
    job_config = {}
    job_snapshot = None
    with jobs_lock:
        job_snapshot = jobs.get(job_id)
        if job_snapshot and job_snapshot.get("results_ready"):
            rows = list(job_snapshot.get("results") or [])
            job_config = dict(job_snapshot.get("job_config") or {})
    if rows is None:
        rows = fetch_subreddits_by_job(job_id)
        if job_snapshot and not job_config:
            job_config = dict(job_snapshot.get("job_config") or {})
    if not job_config:
        job_config = get_job_filters(job_id)
    rows = _apply_job_filters_to_rows(rows, job_config)
    if not rows:
        resp = make_response("No data available for this job yet.")
        resp.status_code = 404
        return resp
    fieldnames = [
        "display_name_prefixed",
        "title",
        "public_description",
        "subscribers",
        "mod_count",
        "is_unmoderated",
        "is_nsfw",
        "last_activity_utc",
        "last_mod_activity_utc",
        "updated_at",
        "url",
        "source",
    ]

    def generate():
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        for row in rows:
            writer.writerow({field: row.get(field) for field in fieldnames})
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    response = Response(generate(), mimetype="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename=subsearch_{job_id}.csv"
    return response


@app.post('/stop/<job_id>')
def stop(job_id):
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            return jsonify({"ok": False, "error": "unknown job"}), 404
        if job.get('done'):
            return jsonify({"ok": False, "error": "already done"}), 400
        current_state = job.get("state")
        job['stop'] = True
    if current_state == "queued":
        removed = _remove_from_queue(job_id)
        with jobs_lock:
            job = jobs.get(job_id)
            if job and removed:
                job['done'] = True
                job['stopped'] = True
                job['state'] = 'stopped'
                job['results_ready'] = False
        if removed:
            record_run_complete(job_id, 0, error="stopped before start")
        return jsonify({"ok": True, "message": "Removed from queue"})
    logger.info("Stop requested for job %s", job_id)
    return jsonify({"ok": True, "message": "Stopping current run"})


@app.route('/helpdocs')
def helpdocs():
    return render_template("help.html", nav_active=None)


@app.route('/docs/developers')
def developer_docs():
    return render_template("developer_docs.html", nav_active=None)


@app.get("/api/subreddits")
def api_subreddits():
    raw_q = request.args.get("q", "")
    q = raw_q.strip()
    q_supplied = raw_q is not None and raw_q.strip() != ""
    raw_unmoderated = request.args.get("unmoderated")
    is_unmoderated = _parse_bool_flag(raw_unmoderated)
    unmoderated_supplied = raw_unmoderated is not None and raw_unmoderated != ""
    raw_nsfw = request.args.get("nsfw")
    nsfw = _parse_bool_flag(raw_nsfw)
    nsfw_supplied = raw_nsfw is not None and raw_nsfw != ""
    raw_min_subs = request.args.get("min_subs")
    min_subs = _safe_int(raw_min_subs)
    min_subs_supplied = raw_min_subs is not None and str(raw_min_subs).strip() != ""
    max_subs = _safe_int(request.args.get("max_subs"))
    page = _safe_int(request.args.get("page"), 1) or 1
    page_size = _safe_int(request.args.get("page_size"), 50) or 50
    sort = request.args.get("sort", "subscribers")
    order = request.args.get("order", "desc")

    job_id_filter = request.args.get("job_id", "").strip()
    run_id_filter = None
    activity_mode = None
    activity_threshold = None
    if job_id_filter:
        run_id_filter = get_run_id_by_job(job_id_filter)
        if run_id_filter is None:
            return jsonify({"total": 0, "page": page, "page_size": page_size, "rows": []})
        job_defaults = get_job_filters(job_id_filter)
        if job_defaults:
            if not q_supplied and job_defaults.get("keyword"):
                q = job_defaults["keyword"]
            if not unmoderated_supplied and job_defaults.get("unmoderated_only"):
                is_unmoderated = True
            if not nsfw_supplied and job_defaults.get("exclude_nsfw"):
                nsfw = False
            if not min_subs_supplied and job_defaults.get("min_subs"):
                min_subs = job_defaults["min_subs"]
            if job_defaults.get("activity_mode") in {"active_after", "inactive_before"}:
                threshold = job_defaults.get("activity_threshold_utc")
                if threshold is not None:
                    activity_mode = job_defaults["activity_mode"]
                    activity_threshold = threshold

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
        run_id=run_id_filter,
        activity_mode=activity_mode,
        activity_threshold_utc=activity_threshold,
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
