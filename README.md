# Sub Search - Reddit Subreddit Discovery Tool

[![GitHub stars](https://img.shields.io/github/stars/ericrosenberg1/reddit-sub-analyzer?style=for-the-badge)](https://github.com/ericrosenberg1/reddit-sub-analyzer/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/ericrosenberg1/reddit-sub-analyzer?style=for-the-badge)](https://github.com/ericrosenberg1/reddit-sub-analyzer/network)
[![GitHub issues](https://img.shields.io/github/issues/ericrosenberg1/reddit-sub-analyzer?style=for-the-badge)](https://github.com/ericrosenberg1/reddit-sub-analyzer/issues)
[![Python](https://img.shields.io/badge/python-3.11+-blue?style=for-the-badge&logo=python)](https://www.python.org/)
[![Django](https://img.shields.io/badge/django-5.2-green?style=for-the-badge&logo=django)](https://www.djangoproject.com/)
[![Reddit API](https://img.shields.io/badge/reddit-API-orange?style=for-the-badge&logo=reddit)](https://www.reddit.com/dev/api/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)
[![Current Version](https://img.shields.io/badge/version-2025.12.03-brightgreen?style=for-the-badge)](VERSION)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=for-the-badge)](CONTRIBUTING.md)

> Discover, analyze, and export Reddit communities with the largest community-maintained subreddit database.

**Sub Search** is an open-source tool for discovering Reddit subreddits with advanced filtering, real-time search progress, and a constantly-growing database of 227,000+ subreddits. Perfect for researchers, marketers, community builders, and Reddit enthusiasts.

[Live Demo](https://allthesubs.ericrosenberg.com) | [Help Center](https://allthesubs.ericrosenberg.com/help/) | [API Docs](https://allthesubs.ericrosenberg.com/developer-docs/)

---

## Features

### Powerful Search
- **Keyword Matching** - Search by keyword in subreddit names, titles, and descriptions
- **Advanced Filters** - Filter by subscriber count, NSFW status, moderator activity, and more
- **Real-Time Progress** - Live updates with ETA calculations as searches run
- **Accumulated Results** - Each search adds to the database, making future searches more valuable

### Smart Automation
- **Priority Queue** - User searches always run first (priority 0), automated searches run when idle (priority 9)
- **Auto-Retry** - Failed searches automatically retry every 10 minutes with medium priority
- **Smart Idle Detection** - Bot triggers random keyword searches after 7 minutes of inactivity
- **Rolling Stats** - 24-hour activity metrics updated every 15 minutes

### Export & Integration
- **CSV Export** - Download all matching subreddits for any keyword
- **REST API** - Programmatic access to the database with filtering and pagination
- **Browse Interface** - Filter, sort, and explore all indexed subreddits

### Volunteer Network
- **Distributed Discovery** - Run your own node to contribute to the database
- **Node Management** - Register, monitor, and manage volunteer nodes
- **Phone Home Sync** - Optionally sync discoveries back to the main database

---

## Quick Start

### Prerequisites

- **Python 3.11+**
- **Redis** (for Celery task queue)
- **PostgreSQL** (recommended) or **SQLite** (development)
- **Reddit API Credentials** ([Get them here](https://www.reddit.com/prefs/apps))

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/ericrosenberg1/reddit-sub-analyzer.git
cd reddit-sub-analyzer

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your credentials (see Configuration below)

# 5. Run database migrations
python manage.py migrate

# 6. Start Redis (in a separate terminal or as a service)
redis-server

# 7. Start Celery worker (in a separate terminal)
celery -A reddit_analyzer worker --loglevel=info

# 8. Start Celery Beat scheduler (in a separate terminal)
celery -A reddit_analyzer beat --loglevel=info

# 9. Run the Django development server
python manage.py runserver
```

Visit `http://localhost:8000`

---

## Architecture

```
+----------------------------------------------------------+
|                  Web Interface                            |
|            (Django Templates + JavaScript)                |
+----------------------------+-----------------------------+
                             |
+----------------------------+-----------------------------+
|                 Django Application                        |
|                                                           |
|  +-------------+  +--------------+  +--------------+     |
|  | Search App  |  |  Nodes App   |  |  Views/API   |     |
|  +-------------+  +--------------+  +--------------+     |
+----------------------------+-----------------------------+
                             |
+----------------------------+-----------------------------+
|           Celery Task Queue (Priority-Based)              |
|                                                           |
|  Priority 0: User searches (immediate)                    |
|  Priority 5: Retried failed searches                      |
|  Priority 9: Auto-ingest & random searches                |
+----------------------------+-----------------------------+
                             |
+----------------------------+-----------------------------+
|                External Integrations                      |
|                                                           |
|  +-------------+  +--------------+  +--------------+     |
|  | Reddit API  |  |  Database    |  |   Redis      |     |
|  |   (PRAW)    |  | PostgreSQL   |  |  (Broker)    |     |
|  +-------------+  +--------------+  +--------------+     |
+----------------------------------------------------------+
```

### Key Components

| Component | Purpose |
|-----------|---------|
| **Django** | Web framework, ORM, admin interface |
| **Celery** | Async task queue with priority levels |
| **Redis** | Message broker and result backend |
| **PRAW** | Reddit API wrapper with rate limiting |
| **PostgreSQL** | Production database (SQLite for dev) |

### Celery Tasks

| Task | Priority | Schedule | Description |
|------|----------|----------|-------------|
| `run_sub_search` | 0 | On-demand | User-submitted searches |
| `retry_errored_searches` | 5 | Every 10 min | Re-queue failed searches |
| `run_random_search` | 9 | When idle 7+ min | Random keyword discovery |
| `run_auto_ingest` | 9 | Every 3 hours | Configured keyword ingestion |
| `cleanup_stale_jobs` | - | Every 5 min | Mark stuck jobs as failed |
| `refresh_rolling_stats` | - | Every 15 min | Update 24h activity metrics |

---

## Configuration

### Required Environment Variables

```bash
# Django
DJANGO_SECRET_KEY=your-secret-key-here
DEBUG=0
ALLOWED_HOSTS=yourdomain.com,localhost

# Reddit API (get from https://www.reddit.com/prefs/apps)
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USERNAME=your_reddit_username      # Optional but recommended
REDDIT_PASSWORD=your_reddit_password      # Optional but recommended

# Database
DATABASE_URL=postgres://user:pass@localhost:5432/subsearch

# Redis
REDIS_URL=redis://localhost:6379/0
```

### Optional Configuration

```bash
# Rate Limiting
SUBSEARCH_RATE_LIMIT_DELAY=0.15          # Seconds between API calls
SUBSEARCH_PUBLIC_API_LIMIT=2000          # Max subreddits per search

# Auto-Ingest
AUTO_INGEST_ENABLED=1
AUTO_INGEST_INTERVAL_MINUTES=180
AUTO_INGEST_KEYWORDS=gaming,technology,science,music

# Random Search
RANDOM_SEARCH_LIMIT=2000

# Email Notifications (optional)
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=your_email
EMAIL_HOST_PASSWORD=your_password
```

See [.env.example](.env.example) for all options.

---

## Production Deployment

### Using Gunicorn + Systemd

```bash
# Install Gunicorn
pip install gunicorn

# Run with Gunicorn
gunicorn reddit_analyzer.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

Create systemd services for:
- Django app (Gunicorn)
- Celery worker
- Celery Beat scheduler

### Using Docker

```bash
docker build -t sub-search .
docker run -d \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  --env-file .env \
  --name sub-search \
  sub-search
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET/POST | Home page with search form |
| `/status/<job_id>/` | GET | Get job status (JSON) |
| `/stop/<job_id>/` | POST | Stop a running search |
| `/job/<job_id>/download.csv` | GET | Download results as CSV |
| `/api/subreddits/` | GET | Search subreddits with filters |
| `/api/recent-runs/` | GET | Recent completed searches |
| `/api/queue/` | GET | Queue status and ETA |
| `/all-the-subs/` | GET | Browse all indexed subreddits |
| `/logs/` | GET | Activity log with search history |

---

## Running a Volunteer Node

Help grow the database by running your own discovery node!

1. Follow the installation steps above
2. Configure your `.env` with Reddit credentials
3. Enable auto-ingest and optionally phone home
4. Register at [allthesubs.ericrosenberg.com/nodes/join](https://allthesubs.ericrosenberg.com/nodes/join)

---

## Contributing

- **Report Bugs** - [Open an issue](https://github.com/ericrosenberg1/reddit-sub-analyzer/issues/new)
- **Submit PRs** - Fix bugs or add features
- **Run a Node** - Help grow the database
- **Improve Docs** - Help make documentation better

---

## Performance

- **Search Speed**: 2-4 minutes for 2000 subreddits
- **Database Size**: 227,000+ subreddits and growing
- **Batch Processing**: Results saved in batches of 32 for efficiency
- **Rate Limiting**: 0.15s delays respect Reddit's API limits

---

## Security

- **Input Sanitization** - All user input validated and sanitized
- **Rate Limiting** - Per-IP limits on API endpoints
- **CSRF Protection** - Django CSRF tokens on all forms
- **Security Headers** - CSP, X-Frame-Options, X-Content-Type-Options

Found a security issue? Please email through the contact form at [ericrosenberg.com](https://ericrosenberg.com) instead of opening a public issue.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- **[PRAW](https://praw.readthedocs.io/)** - Python Reddit API Wrapper
- **[Django](https://www.djangoproject.com/)** - Web framework
- **[Celery](https://docs.celeryproject.org/)** - Distributed task queue
- **[Redis](https://redis.io/)** - In-memory data store

---

<p align="center">
  Made with care by <a href="https://ericrosenberg.com">Eric Rosenberg</a>
  <br>
  <sub>Version <strong>2025.12.03</strong></sub>
</p>
