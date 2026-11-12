# reddit-sub-analyzer (SubSearch) — Claude Code Instructions

## Tech stack
- Django app with Celery for background subreddit analysis tasks
- PostgreSQL + Redis (Celery broker)

## Auto-fix guidelines
- **Test command:** `DJANGO_SECRET_KEY=test python manage.py test --verbosity=0` (settings refuse to load without a key unless `DEBUG=1`)
- Only modify files directly named in the stack trace
- Do not create or modify Django migrations — post a comment on the issue instead
- Do not change Celery task signatures (tasks are serialized in Redis) — post a comment instead
- Sentry DSN in `reddit_analyzer/settings.py` via `REDDIT_ANALYZER_SENTRY_DSN` env var

## File map
- `search/views.py` — HTTP handlers
- `search/tasks.py` — Celery tasks (subreddit analysis)
- `search/models.py` — ORM models (no edits without migration)
- `reddit_analyzer/settings.py` — Django settings
- `nodes/` — federation node management

## CI and release
GitHub Actions is off fleet-wide (2026-09-03) and this repo has no workflow
files. `scripts/ci-gates.sh` runs py_compile, ruff's bug-class rules
(`E9,F63,F7,F82`, blocking), the full ruff report (advisory) and the Django
tests. `.githooks/pre-push` runs it after infra-leak-guard, wired with
`git config core.hooksPath .githooks` (run that once per clone). The gate
needs a venv: `uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt`.
Bypass with `git push --no-verify`.

Nothing runs this app in production as of 2026-10-12. The self-hosted stack
and its `allthesubs.ericrosenberg.com` DNS record are gone, so a push to
`main` is the whole release. `ops/` describes the old webhook deploy, which no
longer exists.
