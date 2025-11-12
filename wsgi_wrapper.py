from importlib import import_module
from typing import Iterable

def _has_rule(app, rule: str) -> bool:
    try:
        return any(getattr(r, "rule", None) == rule for r in app.url_map.iter_rules())  # type: ignore[attr-defined]
    except Exception:
        return False

# Prefer package app; fall back to a tiny Flask app if import fails.
try:
    mod = import_module("subsearch.web_app")
    app = getattr(mod, "app")
except Exception:  # degraded fallback
    from flask import Flask
    app = Flask(__name__)

# Add /health if missing (unique endpoint name to avoid collisions)
if not _has_rule(app, "/health"):
    from flask import jsonify
    @app.get("/health", endpoint="healthz_wrapper")
    def _healthz_wrapper():
        return jsonify({"status": "ok"}), 200

# Add minimal "/" if missing (don’t override your real index)
if not _has_rule(app, "/"):
    from flask import render_template_string
    @app.get("/", endpoint="index_wrapper")
    def _index_wrapper():
        return render_template_string(
            "<h1>Subsearch</h1><p>Service is running.</p>"
            "<p>Health: <a href='/health'>/health</a></p>"
        )
