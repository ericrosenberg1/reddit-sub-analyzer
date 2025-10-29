# Subsearch — Reddit Subreddit Analyzer (Web UI)

Subsearch is a small, private web app for discovering and exporting subreddit lists, with an emphasis on “unmoderated-only” discovery, name keyword search, activity filtering, and quick CSV export. It wraps the Reddit API (via PRAW) with a clean Flask UI that you can run locally or on your own server.

## Features

- Web UI to configure and run scans
- Keyword search on subreddit names
- Toggle: only show unmoderated subreddits
- Exclude NSFW subreddits
- Minimum subscribers filter
- Activity filter (active since / inactive since a date)
- Cap maximum subreddits to check (up to 100,000)
- CSV download on completion (no server-side storing by default)
- Live status updates while running, plus Stop button
- Simple, left-aligned single‑page layout (mobile responsive)

## Quick Start (Local)

Prerequisites:
- Python 3.9+

Install and run with pipx (recommended):

```
pipx install .
subsearch  # runs the web server
```

Or with a virtualenv:

```
python -m venv .venv
source .venv/bin/activate
pip install .
subsearch
```

By default the app listens on http://localhost:5055. Override via `PORT` if desired.

## Configuration

Create a `.env` file next to your install or set environment variables. Minimum required Reddit credentials:

```
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USERNAME=...
REDDIT_PASSWORD=...
REDDIT_USER_AGENT=unmoderated_subreddit_finder/1.0 by /u/<your-username>
```

Or use the built‑in Settings page (top right) to edit and save these values directly to your local `.env`. Secrets are masked and blank fields are ignored (existing values kept). Changes take effect immediately for new runs.

Optional settings:

- `FLASK_SECRET_KEY` — Flask session secret (generate a random string for production)
- `SITE_URL` — Canonical URL (e.g. https://your.domain/subsearch)
- `PORT` — Port to bind (default 5055)
- `REDDIT_TIMEOUT` — HTTP request timeout seconds (default 10)

## Linux Server Install

Use pipx system‑wide for an isolated, upgradable install:

```
# On Debian/Ubuntu
sudo apt update && sudo apt install -y python3-pip python3-venv
python3 -m pip install --user pipx
python3 -m pipx ensurepath

# Clone and install
cd /opt
sudo git clone <your-repo-url> subsearch
cd subsearch
sudo pipx install .
```

Set environment variables for the service (e.g., `/etc/subsearch.env`):

```
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USERNAME=...
REDDIT_PASSWORD=...
REDDIT_USER_AGENT=unmoderated_subreddit_finder/1.0 by /u/yourname
FLASK_SECRET_KEY=change_me
PORT=5055
SITE_URL=https://your.domain/subsearch
```

### systemd Unit (example)

Create `/etc/systemd/system/subsearch.service`:

```
[Unit]
Description=Subsearch Web UI
After=network.target

[Service]
Type=simple
EnvironmentFile=/etc/subsearch.env
ExecStart=/usr/bin/env subsearch
Restart=on-failure
User=www-data
Group=www-data
WorkingDirectory=/var/lib/subsearch

[Install]
WantedBy=multi-user.target
```

Then:

```
sudo mkdir -p /var/lib/subsearch
sudo systemctl daemon-reload
sudo systemctl enable --now subsearch
```

### Reverse Proxy (nginx)

```
server {
    listen 80;
    server_name your.domain;

    location /subsearch/ {
        proxy_pass http://127.0.0.1:5055/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

For HTTPS, use Certbot/Let’s Encrypt as usual.

## Package Layout

- `subsearch/` — installable Python package
  - `web_app.py` — Flask app (+ `run()` entrypoint)
  - `auto_sub_analyzer.py` — Reddit API logic
  - `templates/` — Jinja templates
  - `static/` — CSS and assets
  - `cli.py` — console entrypoint used by `subsearch`
- `pyproject.toml` — packaging metadata
- `README.md` — this file

## Development

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # or `pip install -e .` for editable
python -m subsearch.web_app      # or `subsearch` CLI
```

When running from source, ensure your `.env` is present in the project root.

## Security Notes

- Keep `.env` private; never commit credentials.
- Set a strong `FLASK_SECRET_KEY` in production.
- If exposing publicly, deploy behind a reverse proxy with HTTPS.
- Consider rate limits and Reddit API terms of use.

## License

Proprietary. All rights reserved.
