# Eric Rosenberg Sub Search

![Stars](https://img.shields.io/github/stars/ericrosenberg1/reddit-sub-analyzer?style=for-the-badge&color=ff4500)
![Contributors](https://img.shields.io/github/contributors/ericrosenberg1/reddit-sub-analyzer?style=for-the-badge)
![Last Commit](https://img.shields.io/github/last-commit/ericrosenberg1/reddit-sub-analyzer?style=for-the-badge&color=0ea5e9)
![Security Review](https://img.shields.io/badge/security-review%20passed-success?style=for-the-badge)
![Code Quality](https://img.shields.io/badge/code%20quality-actively%20reviewed-7c3aed?style=for-the-badge)

> All-new Tailwind-powered experience—run it locally or at **[allthesubs.ericrosenberg.com](https://allthesubs.ericrosenberg.com)** to build your personal source of truth for subreddit discovery.

Subsearch is a self-hostable Flask app that wraps the Reddit API with:

- **Homepage**: Project overview, live ingestion stats, and recent run history.
- **Sub Search**: Advanced search with keyword filters, NSFW toggle, unmoderated-only discovery, minimum subscriber gates, activity filters, moderator counts, last moderator activity, and CSV export.
- **All The Subs**: A Reddit-inspired directory backed by SQLite + caching, featuring instant filtering, sorting, pagination, and an `/api/subreddits` endpoint.
- **Automated ingestion**: Background jobs (configurable via env vars) continuously fetch fresh subreddits while honoring Reddit’s API rate limits.

The UI now uses Tailwind CSS with a modern Reddit-adjacent palette, better accessibility, and responsive layouts across all views.

---

## Table of Contents

1. [Highlights](#highlights)
2. [Architecture at a Glance](#architecture-at-a-glance)
3. [Quick Start (Local)](#quick-start-local)
4. [Production Deployment](#production-deployment)
5. [Configuration](#configuration)
6. [Database & Caching](#database--caching)
7. [API & UX](#api--ux)
8. [Security & Code Quality Review](#security--code-quality-review)
9. [Roadmap](#roadmap)
10. [Contributing](#contributing)

---

## Highlights

- **Full-stack coverage**: Homepage → Sub Search → All The Subs, all sharing a cohesive Tailwind design.
- **Live data capture**: Every Sub Search run and auto-ingest cycle writes to SQLite (`data/subsearch.db` by default).
- **Optimized caching**: In-memory TTL caches keep summary stats and All The Subs queries snappy while respecting low-traffic constraints.
- **Safe exports**: CSVs are generated in sandboxed temp directories with sanitized filenames.
- **Open-source invites**: Clear calls to action for GitHub issues/PRs plus README badges inspired by the Immich project.

---

## Architecture at a Glance

| Layer | Role | Tech |
| --- | --- | --- |
| UI | Tailwind CSS, modern Reddit-inspired layout, responsive components | Flask + Jinja templates |
| API | `/api/subreddits` JSON endpoint with filtering/pagination | Flask Blueprint |
| Jobs | Manual Sub Search + automated auto-ingest thread (interval + keyword aware) | `praw`, background thread |
| Persistence | SQLite (WAL mode) storing `query_runs` + `subreddits` | `sqlite3`, custom DAO |
| Caching | TTL caches for summary data + search responses, invalidated on write | `subsearch.cache.TTLCache` |

---

## Quick Start (Local)

Prereqs: **Python 3.9+**

```bash
git clone https://github.com/ericrosenberg1/reddit-sub-analyzer.git
cd reddit-sub-analyzer
python -m venv .venv && source .venv/bin/activate
pip install -e .
subsearch  # defaults to http://localhost:5055
```

Or install with `pipx`:

```bash
pipx install .
subsearch
```

Tips:

- `which subsearch` to confirm whether you’re running the pipx binary or a local venv version.
- Run the binary from the folder where you want `.env` and `data/subsearch.db` maintained.

---

## Production Deployment

1. **Install system-wide** (Debian/Ubuntu example):
   ```bash
   sudo apt update && sudo apt install -y python3-pip python3-venv
   python3 -m pip install --user pipx
   python3 -m pipx ensurepath
   sudo git clone https://github.com/ericrosenberg1/reddit-sub-analyzer.git /opt/subsearch
   cd /opt/subsearch && sudo pipx install .
   ```
2. **Environment file** (`/etc/subsearch.env`):
   ```env
   REDDIT_CLIENT_ID=...
   REDDIT_CLIENT_SECRET=...
   REDDIT_USERNAME=...
   REDDIT_PASSWORD=...
   REDDIT_USER_AGENT=unmoderated_subreddit_finder/1.0 by /u/yourname
   FLASK_SECRET_KEY=change_me
   SITE_URL=https://allthesubs.ericrosenberg.com
   PORT=5055
   AUTO_INGEST_INTERVAL_MINUTES=60
   AUTO_INGEST_LIMIT=2000
   AUTO_INGEST_DELAY_SEC=0.3
   ```
3. **systemd unit** (`/etc/systemd/system/subsearch.service`):
   ```ini
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
   ```bash
   sudo mkdir -p /var/lib/subsearch
   sudo systemctl daemon-reload
   sudo systemctl enable --now subsearch
   ```
4. **Reverse proxy (nginx)**:
   ```nginx
   server {
       listen 80;
       server_name allthesubs.ericrosenberg.com;

       location / {
           proxy_pass http://127.0.0.1:5055/;
           proxy_set_header Host $host;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```
5. **HTTPS**: `sudo certbot --nginx -d allthesubs.ericrosenberg.com`

### Automated Deploys (Webhook + Script)

After the first manual install you can let GitHub push events redeploy the app automatically:

1. **Install the deploy helper.** Copy `scripts/deploy_subsearch.sh` to the server and install it system-wide:
   ```bash
   sudo install -m 0755 scripts/deploy_subsearch.sh /usr/local/bin/deploy_subsearch.sh
   # Optional: keep overrides in /etc/subsearch-deploy.env
   ```
   The script accepts overrides via env vars (`APP_DIR`, `APP_USER`, `VENV_PATH`, `BRANCH`, `SERVICE_NAME`, `PIP_FLAGS`). Run it once manually to confirm the service restarts cleanly:
   ```bash
   sudo APP_DIR=/opt/subsearch APP_USER=subsearch SERVICE_NAME=subsearch /usr/local/bin/deploy_subsearch.sh
   ```

2. **Provision the webhook listener.** Install the lightweight [`webhook`](https://github.com/adnanh/webhook) binary (`sudo apt install webhook`), then place the sample config + service from `ops/webhook/subsearch-webhook.json` and `ops/systemd/subsearch-webhook.service`. Adjust paths/ports as needed and keep the config in `/opt/subsearch/hooks/subsearch-webhook.json`. Store the shared secret outside git:
   ```bash
   echo "super-long-random-string" | sudo tee /etc/subsearch-webhook.secret
   sudo systemctl enable --now subsearch-webhook
   ```

3. **Wire up GitHub.** In your repo settings add a webhook pointing to `https://allthesubs.ericrosenberg.com/hooks/subsearch-deploy`, choose `application/json`, limit it to push events, and paste the same secret. The `webhook` daemon validates the `X-Hub-Signature-256` header before executing `/usr/local/bin/deploy_subsearch.sh`, so every push to `main` automatically fetches, reinstalls, and restarts the `subsearch` service.

If you prefer polling-based automation, point a cron entry at `/usr/local/bin/deploy_subsearch.sh` instead of using the webhook listener.

---

## Configuration

Copy `.env.example`, fill in the blanks, and keep the file out of version control. Sub Search never exposes secrets in the UI.

### Core runtime

| Variable | Default | Description |
| --- | --- | --- |
| `FLASK_SECRET_KEY` | `dev-secret-key` | Override before going to production. |
| `SITE_URL` | `` | Used for canonical links + phone home metadata. |
| `PORT` | `5055` | HTTP port for `subsearch-web`. |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` / `REDDIT_USERNAME` / `REDDIT_PASSWORD` / `REDDIT_USER_AGENT` | — | Script app credentials for Reddit’s API. |
| `REDDIT_TIMEOUT` | `10` | Timeout (seconds) for API calls. |

### Database & storage

| Variable | Default | Description |
| --- | --- | --- |
| `DB_TYPE` | `sqlite` | `sqlite` (default) or `postgres`. |
| `SUBSEARCH_BASE_DIR`, `SUBSEARCH_DATA_DIR`, `SUBSEARCH_DB_PATH` | `./data/subsearch.db` | Override where SQLite lives. |
| `DB_POSTGRES_HOST`, `DB_POSTGRES_PORT`, `DB_POSTGRES_DB`, `DB_POSTGRES_USER`, `DB_POSTGRES_PASSWORD`, `DB_POSTGRES_SSLMODE` | — | Required when `DB_TYPE=postgres`. Missing values raise a startup error with clear instructions so admins can fix the install. |

### Search runtime controls

| Variable | Default | Description |
| --- | --- | --- |
| `SUBSEARCH_MAX_CONCURRENT_JOBS` | `1` | How many manual Sub Search jobs can run at once; additional requests wait in a visible queue. |
| `SUBSEARCH_RATE_LIMIT_DELAY` | `0.2` | Seconds to pause between subreddit lookups. Lower it for faster runs, raise it if you want extra buffer against Reddit API limits. |

### Auto-ingest

| Variable | Default | Description |
| --- | --- | --- |
| `AUTO_INGEST_ENABLED` | `1` | Toggle the scheduler. |
| `AUTO_INGEST_INTERVAL_MINUTES` | `180` (min 15) | Sleep window between runs. |
| `AUTO_INGEST_LIMIT` | `1000` (100–5000) | Subreddits per cycle. |
| `AUTO_INGEST_MIN_SUBS` | `0` | Minimum subscriber count to persist. |
| `AUTO_INGEST_DELAY_SEC` | `0.25` | Delay between API hits. |
| `AUTO_INGEST_KEYWORDS` | `` | Optionally seed comma-separated keywords. |

### Volunteer node email + pruning

| Variable | Default | Description |
| --- | --- | --- |
| `NODE_EMAIL_SENDER`, `NODE_EMAIL_SENDER_NAME` | — | From-address for volunteer node links. |
| `NODE_EMAIL_SMTP_HOST`, `NODE_EMAIL_SMTP_PORT`, `NODE_EMAIL_SMTP_USERNAME`, `NODE_EMAIL_SMTP_PASSWORD`, `NODE_EMAIL_USE_TLS` | — | SMTP connection info (required to email unique node links). |
| `NODE_CLEANUP_INTERVAL_SECONDS` | `86400` | Background job cadence for pruning broken nodes. |
| `NODE_BROKEN_RETENTION_DAYS` | `7` | Automatically delete nodes that stay broken this long. |

### Phone-home federation

| Variable | Default | Description |
| --- | --- | --- |
| `PHONE_HOME` | `false` | Enable opt-in sync to allthesubs.ericrosenberg.com. |
| `PHONE_HOME_ENDPOINT` | hosted API URL | Override when testing a different collector. |
| `PHONE_HOME_TOKEN` | `` | Optional bearer token for authenticated sync. |
| `PHONE_HOME_TIMEOUT` | `10` | Seconds to wait before abandoning a sync POST. |
| `PHONE_HOME_BATCH_MAX` | `500` | Max records to include per batch. |
| `PHONE_HOME_SOURCE` | `self-hosted` | Label that upstream uses when storing your data. |

Configuration updates stay in the `.env`; distribute secrets through your deployment tooling so credentials never touch the UI.

---

## Build Numbers

Every deployment advertises a playful build number in the site footer. The number lives in `subsearch/BUILD_NUMBER` and follows `YYYY.MM.sequence`:

- First Sub Search deploy in November 2025 → `2025.11.1`
- Second deploy that same month → `2025.11.2`

Bump the build number whenever you cut a release:

```bash
python3 -m subsearch.build_info
git add subsearch/BUILD_NUMBER
```

The helper reads, increments, and persists the correct sequence per month, so you never have to edit the file by hand.

---

## Database & Caching

- SQLite operates in **WAL mode** for concurrent reads + writes.
- Tables:
  - `query_runs`: job metadata (manual + auto-ingest) with duration, status, and errors.
  - `subreddits`: deduplicated subreddit rows with moderation flags, NSFW state, subscriber counts, last activity, and provenance.
- **TTL caches** back summary stats and All The Subs queries. Whenever subreddits are persisted or a run is recorded, caches invalidate to keep results consistent.
- Swap databases without code changes: set `DB_TYPE=postgres` plus the Postgres env vars and Sub Search will connect via psycopg2 with the same UPSERT logic.
- Every `persist_subreddits` call performs an upsert, updating titles/descriptions/mod activity timestamps without ever duplicating a subreddit row.
- Low-traffic friendly caching avoids hammering SQLite; when you move to Postgres the same DAO and caches continue to work.

---

## API & UX

- `GET /api/subreddits`: JSON response with total count, pagination metadata, and filtered row data. Parameters:
  - `q`, `min_subs`, `max_subs`, `unmoderated`, `nsfw`, `sort`, `order`, `page`, `page_size`.
- Frontend powered by Tailwind + CDN (no build step) with custom Reddit-like gradients and glassmorphism touches.
- Sub Search form preserves inputs for an hour locally, provides live status updates, and prevents path traversal with strict server-side validation.

## Phone-home Federation

- Opt-in by setting `PHONE_HOME=true`. Each time `persist_subreddits` stores fresh data, a background thread streams a sanitized batch (names, moderation metadata, last activity timestamps) to `PHONE_HOME_ENDPOINT` (defaults to `https://allthesubs.ericrosenberg.com/api/ingest`).
- Include `PHONE_HOME_TOKEN` if the hosted service assigns you a bearer token; otherwise the sync runs anonymously and still helps the canonical directory grow.
- Batches are capped by `PHONE_HOME_BATCH_MAX` and respect `PHONE_HOME_TIMEOUT` so your local runs keep moving even if the hosted API is slow.
- This collaboration pipeline lets self-hosted installs contribute to the “big sandwich” dataset without manual exports.

---

## Security & Code Quality Review

✅ **Security**
- Server-side validation for numeric limits, filenames, and activity dates.
- Download endpoints only serve Sub Search-generated files tied to known job IDs.
- Background ingestion honors Reddit rate limits (configurable delay + max fetches).
- Secrets live in `.env`; deploy updates through your preferred secret management workflow so the UI never touches Reddit credentials.

✅ **Code Quality & Performance**
- Modular storage layer with isolated database + cache utilities, reducing duplication.
- TTL caching improves `/api/subreddits` latency while auto-invalidating on writes.
- Tailwind UI removes legacy CSS duplication and aligns copy with the new experience.
- Grammar + messaging refreshed across templates and README for clarity.

Open risks / future ideas:
- Optional switch to PostgreSQL for multi-user, high-write installs.
- Add integration tests around `/api/subreddits`.
- Consider pagination-size guards exposed to the client.

---

## Roadmap

1. Authenticated dashboards (multi-user access control).
2. Saved filter presets for All The Subs.
3. Export to Google Sheets / Airtable.
4. Webhook or email notifications when auto-ingest discovers notable subs.

---

## Helpdocs

Deployment, environment, and contributor docs live in the repository README and the `#helpdocs` anchor: <https://github.com/ericrosenberg1/reddit-sub-analyzer#helpdocs>. Link to that section from any UI surfaces (footer, settings pages, etc.) so admins always have a canonical reference.

---

## Contributing

1. Fork + clone
2. Create a feature branch
3. `pip install -e .` and run `subsearch`
4. Submit a PR with screenshots / notes

Need help or have an idea? Open an issue or ping me on GitHub. Let’s build the most complete and respectful subreddit directory on the internet. 🚀
