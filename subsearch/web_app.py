import os
import json
import logging
import threading
import tempfile
import re
from datetime import datetime, timezone

from flask import Flask, render_template, request, send_file, flash, redirect, url_for, session, make_response, jsonify
from dotenv import load_dotenv

# Reuse core analyzer functions
from .auto_sub_analyzer import find_unmoderated_subreddits, save_to_csv


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

# Restrict directory browsing removed (no server-side saving)
BASE_DIR = os.path.abspath(os.getcwd())
SITE_URL = os.getenv("SITE_URL", "")


def default_output_filename():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"unmoderated_subreddits_{timestamp}.csv"


@app.route("/", methods=["GET", "POST"])
def index():
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
            return render_template("index.html", result=None, job_id=None, site_url=SITE_URL)

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
            return render_template("index.html", result=None, job_id=None, site_url=SITE_URL)

        # Activity date filter
        activity_threshold_utc = None
        if activity_enabled and activity_mode in ("active_after", "inactive_before") and activity_date_raw:
            # Expect YYYY-MM-DD
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", activity_date_raw):
                flash("Invalid date format. Use YYYY-MM-DD.", "error")
                return render_template("index.html", result=None, job_id=None, site_url=SITE_URL)
            try:
                dt = datetime.strptime(activity_date_raw, "%Y-%m-%d")
                activity_threshold_utc = int(dt.timestamp())
            except Exception:
                flash("Invalid date provided.", "error")
                return render_template("index.html", result=None, job_id=None, site_url=SITE_URL)
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
            }

        def run_job():
            logger.info(f"Job {job_id} started: keyword=%r limit=%d unmoderated_only=%s output_dir=%r file_name=%r",
                        keyword, limit, unmoderated_only, None, file_name)
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
                with jobs_lock:
                    jobs[job_id]['done'] = True
                    jobs[job_id]['output_path'] = os.path.abspath(output_path)
                    jobs[job_id]['found'] = len(subs)
                    if jobs[job_id].get('stop'):
                        jobs[job_id]['stopped'] = True
                logger.info(f"Job {job_id} finished: saved to %s (found=%d)", output_path, len(subs))
            except Exception as e:
                logger.exception("Job %s errored", job_id)
                with jobs_lock:
                    jobs[job_id]['error'] = str(e)
                    jobs[job_id]['done'] = True

        t = threading.Thread(target=run_job, daemon=True)
        t.start()
        # Redirect to page with job param so client can poll
        return redirect(url_for('index', job=job_id))

    return render_template("index.html", result=result, job_id=job_id, site_url=SITE_URL)


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
        return redirect(url_for("index"))
    if not os.path.exists(path):
        flash("File not found for download.", "error")
        return redirect(url_for("index"))
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
    # Masked redirect to external help (rick roll)
    return redirect('https://www.youtube.com/watch?v=dQw4w9WgXcQ', code=302)


def run():
    # Run on a non-standard port for easy access
    port = int(os.getenv("PORT", "5055"))
    # Elevate logging when running in debug mode
    logger.setLevel(logging.DEBUG)
    logging.getLogger("analyzer").setLevel(logging.DEBUG)
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    run()
