# reddit-sub-analyzer (SubSearch) — Claude Code Instructions

## Tech stack
- Django app with Celery for background subreddit analysis tasks
- PostgreSQL + Redis (Celery broker)

## Auto-fix guidelines
- **Test command:** `python manage.py test --verbosity=0`
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