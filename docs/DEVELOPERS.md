# Sub Search Developer Documentation

Technical documentation for contributors, developers, and system administrators working with Sub Search.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Technology Stack](#technology-stack)
3. [Installation & Setup](#installation--setup)
4. [Project Structure](#project-structure)
5. [Core Components](#core-components)
6. [Database Schema](#database-schema)
7. [API Reference](#api-reference)
8. [Configuration](#configuration)
9. [Background Workers](#background-workers)
10. [Performance Optimization](#performance-optimization)
11. [Testing](#testing)
12. [Deployment](#deployment)
13. [Contributing](#contributing)
14. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

Sub Search is a Flask-based web application that combines real-time Reddit API searches with a persistent subreddit database.

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      Web Interface                       │
│              (Flask + Tailwind CSS + HTMX)              │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────┐
│                  Core Application                        │
│                  (Python + Flask)                        │
│                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │   Search    │  │   Queue     │  │   Storage   │    │
│  │   Engine    │  │   Manager   │  │   Layer     │    │
│  └─────────────┘  └─────────────┘  └─────────────┘    │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────┐
│                External Integrations                     │
│                                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │   Reddit    │  │   Database  │  │ Phone Home  │    │
│  │     API     │  │  SQLite/PG  │  │   Sync      │    │
│  └─────────────┘  └─────────────┘  └─────────────┘    │
└─────────────────────────────────────────────────────────┘
```

### Key Design Principles

1. **Dual Data Sources** - Combine cached database results with fresh API data
2. **Background Processing** - Long-running searches execute in worker threads
3. **Queue Management** - Multiple concurrent searches with automatic queuing
4. **Real-Time Updates** - JavaScript polling for live progress tracking
5. **Caching Layer** - In-memory TTL cache for frequent queries
6. **Distributed Architecture** - Support for volunteer nodes with phone home

---

## Technology Stack

### Backend

- **Python 3.11+** - Core language
- **Flask 3.0+** - Web framework
- **PRAW 7.7+** - Python Reddit API Wrapper
- **SQLite** - Default database (development)
- **PostgreSQL** - Optional production database
- **Threading** - Concurrent job execution

### Frontend

- **Tailwind CSS** - Utility-first CSS framework
- **Vanilla JavaScript** - Real-time updates and animations
- **Jinja2 Templates** - Server-side rendering

### Development Tools

- **pytest** - Testing framework
- **black** - Code formatting
- **flake8** - Linting
- **mypy** - Type checking

---

## Installation & Setup

### Prerequisites

```bash
# System requirements
python --version  # 3.11 or higher
git --version     # Any recent version

# Optional for PostgreSQL
psql --version    # 12 or higher
```

### Local Development Setup

```bash
# 1. Clone repository
git clone https://github.com/ericrosenberg1/reddit-sub-analyzer.git
cd reddit-sub-analyzer

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your Reddit API credentials

# 5. Initialize database
python -c "from subsearch.storage import init_db; init_db()"

# 6. Run development server
export FLASK_DEBUG=1
python -m subsearch.web_app
```

### Reddit API Credentials

1. Visit https://www.reddit.com/prefs/apps
2. Click "Create App" or "Create Another App"
3. Fill in details:
   - **Name:** Your app name
   - **Type:** script
   - **Redirect URI:** http://localhost:8080
4. Save `client_id` and `client_secret` to `.env`

### Environment Variables

Required variables in `.env`:

```bash
# Reddit API (Required)
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_secret_here
REDDIT_USER_AGENT=SubSearch/1.0

# Optional: For authenticated access
REDDIT_USERNAME=your_reddit_username
REDDIT_PASSWORD=your_reddit_password

# Flask Configuration
FLASK_SECRET_KEY=random_secret_key_here
SUBSEARCH_PORT=5055

# Database (Default: SQLite)
SUBSEARCH_DB_TYPE=sqlite
SUBSEARCH_DB_PATH=./data/subreddits.db
```

---

## Project Structure

```
reddit-sub-analyzer/
├── subsearch/              # Main package
│   ├── __init__.py
│   ├── web_app.py         # Flask application & routes
│   ├── auto_sub_analyzer.py  # Reddit API search logic
│   ├── storage.py         # Database operations
│   ├── config.py          # Configuration management
│   ├── cache.py           # In-memory caching
│   ├── build_info.py      # Version management (legacy)
│   ├── phone_home.py      # Node sync functionality
│   ├── templates/         # Jinja2 templates
│   │   ├── base.html
│   │   ├── home.html
│   │   ├── index.html    # Sub Search page
│   │   ├── all_subs.html
│   │   ├── logs.html
│   │   └── nodes/
│   └── static/           # CSS, JS, images
│       ├── styles.css
│       └── img/
├── docs/                 # Documentation
│   ├── HELP.md
│   ├── DEVELOPERS.md
│   ├── API.md
│   └── CHANGELOG.md
├── scripts/              # Utility scripts
│   ├── bump_version.py
│   └── apply_overhaul.sh
├── data/                 # Database & cache (gitignored)
├── tests/                # Test suite
├── VERSION               # Current version file
├── .env.example          # Environment template
├── requirements.txt      # Python dependencies
├── Dockerfile           # Container configuration
└── README.md            # Project overview
```

---

## Core Components

### 1. Search Engine (`auto_sub_analyzer.py`)

The search engine queries Reddit's API with intelligent rate limiting.

**Key Function:**

```python
def find_unmoderated_subreddits(
    limit: int = 1000,
    name_keyword: Optional[str] = None,
    unmoderated_only: bool = False,
    exclude_nsfw: bool = False,
    min_subscribers: int = 0,
    activity_mode: str = "any",
    activity_threshold_utc: Optional[int] = None,
    progress_callback: Optional[Callable] = None,
    stop_callback: Optional[Callable] = None,
    rate_limit_delay: float = 0.15,
    include_all: bool = True,
    exclude_names: Optional[Set[str]] = None,
    result_callback: Optional[Callable] = None,
) -> Dict:
    """
    Search Reddit for subreddits matching criteria.

    Returns:
        {
            "results": List[Dict],      # Filtered results
            "evaluated": List[Dict],    # All evaluated subs
        }
    """
```

**Rate Limiting:**
- Default delay: 0.15 seconds between API calls
- Configurable via `SUBSEARCH_RATE_LIMIT_DELAY`
- Respects Reddit's 60 requests/minute limit

**Search Strategy:**
1. Query `/subreddits/search` endpoint with keyword
2. Filter by subscriber count, NSFW status, mod status
3. Check activity timestamps if required
4. Yield results via callback for streaming storage

### 2. Queue Manager (`web_app.py`)

Manages concurrent search jobs with automatic queuing.

**Data Structures:**

```python
jobs = {}                    # Dict[job_id, job_data]
job_queue = deque()          # FIFO queue for pending jobs
running_jobs = set()         # Currently executing job IDs
```

**Job Lifecycle:**

```python
# 1. Job Creation
job_id = uuid.uuid4().hex
jobs[job_id] = {
    "job_id": job_id,
    "state": "queued",
    "checked": 0,
    "found": 0,
    "results": [],
    ...
}

# 2. Enqueue
_enqueue_job(job_id)
_start_jobs_if_possible()

# 3. Execution
def _run_job_thread(job_id):
    # Database search
    # API search
    # Persist results

# 4. Completion
record_run_complete(job_id, result_count, error)
```

**ETA Calculation:**

```python
def _calculate_average_job_time():
    """Calculate ETA based on recent job history."""
    recent = fetch_recent_runs(limit=10, source_filter="sub_search")
    durations = []
    for run in recent:
        started = parse_iso(run.get("started_at"))
        completed = parse_iso(run.get("completed_at"))
        if started and completed:
            delta = (completed - started).total_seconds()
            durations.append(delta)
    return sum(durations) / len(durations) if durations else 60
```

### 3. Storage Layer (`storage.py`)

Handles all database operations with SQLite/PostgreSQL support.

**Connection Management:**

```python
@contextmanager
def db_conn():
    """Context manager for database connections."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

**Key Functions:**

```python
# Job tracking
record_run_start(job_id, params, source)
record_run_complete(job_id, result_count, error)

# Subreddit persistence
persist_subreddits(job_id, subreddits, keyword, source)

# Search queries
search_subreddits(
    q=keyword,
    is_unmoderated=True,
    min_subs=1000,
    page=1,
    page_size=50
)

# Cleanup operations
cleanup_stale_runs(max_age_hours=24)
prune_broken_nodes(max_age_days=7)
```

### 4. Caching Layer (`cache.py`)

In-memory TTL cache for frequent queries.

```python
class TTLCache:
    """Simple in-memory cache with time-based expiration."""

    def __init__(self, ttl_seconds: int):
        self.ttl = ttl_seconds
        self.cache = {}

    def get(self, key):
        entry = self.cache.get(key)
        if entry and time.time() - entry["time"] < self.ttl:
            return entry["value"]
        return None

    def set(self, key, value):
        self.cache[key] = {"value": value, "time": time.time()}
```

**Cache Instances:**

```python
summary_cache = TTLCache(60)          # Database stats
recent_runs_cache = TTLCache(10)      # Recent job history
search_cache = TTLCache(300)          # Search results
nodes_cache = TTLCache(60)            # Volunteer nodes
```

---

## Database Schema

### SQLite Schema

#### `query_runs` Table

Tracks all search jobs (manual, auto-ingest, random).

```sql
CREATE TABLE query_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT UNIQUE NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    keyword TEXT,
    limit_value INTEGER,
    unmoderated_only INTEGER NOT NULL DEFAULT 1,
    exclude_nsfw INTEGER NOT NULL DEFAULT 0,
    min_subscribers INTEGER NOT NULL DEFAULT 0,
    activity_mode TEXT,
    activity_threshold_utc INTEGER,
    file_name TEXT,
    result_count INTEGER DEFAULT 0,
    duration_ms INTEGER,
    error TEXT
);
```

**Indexes:**
- `job_id` - UNIQUE for quick job lookups

#### `subreddits` Table

Stores subreddit data with automatic deduplication.

```sql
CREATE TABLE subreddits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    display_name_prefixed TEXT,
    title TEXT,
    public_description TEXT,
    url TEXT,
    subscribers INTEGER,
    is_unmoderated INTEGER NOT NULL DEFAULT 0,
    is_nsfw INTEGER NOT NULL DEFAULT 0,
    last_activity_utc INTEGER,
    last_mod_activity_utc INTEGER,
    mod_count INTEGER,
    last_seen_run_id INTEGER,
    last_keyword TEXT,
    source TEXT,
    first_seen_at TEXT,
    updated_at TEXT,
    FOREIGN KEY(last_seen_run_id) REFERENCES query_runs(id) ON DELETE SET NULL
);
```

**Indexes:**
- `name` - UNIQUE for deduplication
- `subscribers DESC` - Fast sorting by popularity
- `updated_at DESC` - Recent updates first
- `(is_unmoderated, subscribers DESC)` - Composite index for unmoderated queries

#### `volunteer_nodes` Table

Manages community-contributed nodes.

```sql
CREATE TABLE volunteer_nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL,
    reddit_username TEXT,
    location TEXT,
    system_details TEXT,
    availability TEXT,
    bandwidth_notes TEXT,
    notes TEXT,
    health_status TEXT NOT NULL DEFAULT 'pending',
    last_check_in_at TEXT,
    broken_since TEXT,
    manage_token TEXT UNIQUE NOT NULL,
    manage_token_sent_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    deleted_at TEXT
);
```

**Indexes:**
- `manage_token` - UNIQUE for authentication
- `(health_status, updated_at DESC)` - Filter active nodes

### PostgreSQL Schema

PostgreSQL schema is nearly identical with these differences:

- `SERIAL PRIMARY KEY` instead of `INTEGER PRIMARY KEY AUTOINCREMENT`
- `BIGINT` for Unix timestamps (larger range)
- Named parameters use `%(param)s` instead of `:param`

---

## API Reference

### REST API Endpoints

#### GET `/api/recent-runs`

Fetch recent search jobs.

**Parameters:**
- `limit` (int, optional) - Number of runs to return (1-50, default: 5)
- Example: `/api/recent-runs?limit=10`

**Response:**
```json
{
  "runs": [
    {
      "job_id": "abc123",
      "source": "sub_search",
      "started_at": "2025-11-12T10:30:00",
      "completed_at": "2025-11-12T10:35:00",
      "keyword": "gaming",
      "result_count": 150,
      "error": null,
      "limit_value": 1000
    }
  ]
}
```

#### GET `/api/subreddits`

Search the database with filters.

**Parameters:**
- `q` (string) - Keyword search
- `unmoderated` (boolean) - Filter by moderation status
- `nsfw` (boolean) - NSFW filter (true=include, false=exclude)
- `min_subs` (int) - Minimum subscriber count
- `max_subs` (int) - Maximum subscriber count
- `sort` (string) - Sort field (subscribers, name, title, updated_at)
- `order` (string) - Sort direction (asc, desc)
- `page` (int) - Page number (default: 1)
- `page_size` (int) - Results per page (1-200, default: 50)
- `job_id` (string) - Filter by specific job

**Example:**
```
/api/subreddits?q=gaming&min_subs=10000&nsfw=false&page=1&page_size=20
```

**Response:**
```json
{
  "total": 523,
  "page": 1,
  "page_size": 20,
  "rows": [
    {
      "name": "gaming",
      "display_name_prefixed": "r/gaming",
      "title": "r/gaming - Discussion and News",
      "subscribers": 38500000,
      "is_unmoderated": false,
      "is_nsfw": false,
      ...
    }
  ]
}
```

#### GET `/status/<job_id>`

Get real-time status of a running job.

**Response:**
```json
{
  "job_id": "abc123",
  "state": "running",
  "checked": 500,
  "found": 75,
  "done": false,
  "error": null,
  "queue_position": null,
  "eta_seconds": 0,
  "progress_phase": "api_search",
  "queue_backlog": 2,
  "max_concurrent": 3
}
```

#### POST `/stop/<job_id>`

Stop a running or queued job.

**Response:**
```json
{
  "ok": true,
  "message": "Stopping current run"
}
```

---

## Configuration

### Environment Variables

See [`.env.example`](.env.example) for complete reference.

**Core Settings:**

```bash
# Reddit API
REDDIT_CLIENT_ID=required
REDDIT_CLIENT_SECRET=required
REDDIT_USERNAME=optional
REDDIT_PASSWORD=optional

# Application
FLASK_SECRET_KEY=random_secret_key
SUBSEARCH_PORT=5055
SUBSEARCH_SITE_URL=https://yoursite.com

# Performance
SUBSEARCH_RATE_LIMIT_DELAY=0.15
SUBSEARCH_PUBLIC_API_LIMIT=2000
SUBSEARCH_MAX_CONCURRENT_JOBS=3
SUBSEARCH_JOB_TIMEOUT_SECONDS=600

# Database
SUBSEARCH_DB_TYPE=sqlite
SUBSEARCH_DB_PATH=./data/subreddits.db

# Auto-Ingest
AUTO_INGEST_ENABLED=1
AUTO_INGEST_INTERVAL_MINUTES=180
AUTO_INGEST_LIMIT=2000
AUTO_INGEST_KEYWORDS=gaming,technology,science

# Random Search
RANDOM_SEARCH_ENABLED=1
RANDOM_SEARCH_INTERVAL_MINUTES=60
RANDOM_SEARCH_LIMIT=1000

# Phone Home
PHONE_HOME=false
PHONE_HOME_ENDPOINT=https://main-server.com/api/ingest
```

### Configuration Validation

The `config.py` module validates all settings on startup:

```python
def get_config_warnings() -> List[str]:
    """Return list of configuration warnings."""
    warnings = []

    if not REDDIT_CLIENT_ID:
        warnings.append("Reddit CLIENT_ID not configured")

    if RATE_LIMIT_DELAY < 0.1:
        warnings.append("Rate limit delay too low, may hit API limits")

    return warnings
```

---

## Background Workers

### Auto-Ingest Worker

Runs scheduled searches to continuously grow the database.

```python
def _auto_ingest_loop():
    """Background thread for scheduled searches."""
    keywords = AUTO_INGEST_KEYWORDS or [None]
    interval_seconds = AUTO_INGEST_INTERVAL_MINUTES * 60

    while True:
        for keyword in keywords:
            _run_auto_ingest_job(keyword)
        time.sleep(interval_seconds)
```

**Configuration:**

```bash
AUTO_INGEST_ENABLED=1
AUTO_INGEST_INTERVAL_MINUTES=180  # Run every 3 hours
AUTO_INGEST_LIMIT=2000           # Check 2000 subs per run
AUTO_INGEST_KEYWORDS=gaming,technology,science
```

### Random Search Worker

Discovers new subreddits using random keywords.

```python
def _random_search_loop():
    """Background thread for random keyword searches."""
    while RANDOM_SEARCH_ENABLED:
        keyword = _fetch_random_keyword()
        _schedule_random_job(keyword)
        time.sleep(RANDOM_SEARCH_INTERVAL_MINUTES * 60)
```

**Random Word API:**

```bash
RANDOM_WORD_API=https://random-word-api.herokuapp.com/word
```

Falls back to built-in word list if API unavailable.

### Node Cleanup Worker

Removes stale data and broken nodes.

```python
def _node_cleanup_loop():
    """Nightly cleanup of broken nodes and stale jobs."""
    while True:
        # Remove broken nodes older than 7 days
        removed = prune_broken_nodes(NODE_BROKEN_RETENTION_DAYS)

        # Mark jobs stuck in running state as failed
        stale_count = cleanup_stale_runs(max_age_hours=24)

        time.sleep(NODE_CLEANUP_INTERVAL_SECONDS)
```

**Cleanup Operations:**

1. **Stale Runs** - Jobs stuck in "running" state for 24+ hours
2. **Broken Nodes** - Nodes marked broken for 7+ days
3. **Cache Invalidation** - Clears all caches after cleanup

---

## Performance Optimization

### Historical Improvements

**Version 1.0 → 2025.11.01.0:**
- Search time: 8-12 minutes → 2-4 minutes (60-75% improvement)
- Removed moderator activity checks (eliminated 8000 API calls)
- Reduced rate limit delay 0.2s → 0.15s
- Added ETA calculations for better UX

### Current Performance Metrics

- **Database Query:** < 1 second for most searches
- **API Search (1000 subs):** 2-4 minutes
- **API Search (2000 subs):** 4-8 minutes
- **Concurrent Jobs:** Up to 3 simultaneous searches

### Optimization Techniques

**1. Database Indexing**

```sql
-- Critical indexes for query performance
CREATE INDEX idx_subreddits_subscribers ON subreddits(subscribers DESC);
CREATE INDEX idx_subreddits_unmod ON subreddits(is_unmoderated, subscribers DESC);
```

**2. Batch Persistence**

```python
PERSIST_BATCH_SIZE = 100  # Commit every 100 subreddits

def _persist_worker(queue, job_id, keyword, source):
    """Background thread for batched database writes."""
    buffer = []
    while True:
        item = queue.get()
        if item is None:
            break
        buffer.append(item)
        if len(buffer) >= PERSIST_BATCH_SIZE:
            persist_subreddits(job_id, buffer, keyword, source)
            buffer.clear()
```

**3. Query Caching**

```python
# Cache search results for 5 minutes
search_cache = TTLCache(300)

def search_subreddits(...):
    cache_key = ("search", q, is_unmoderated, ...)
    cached = search_cache.get(cache_key)
    if cached:
        return cached
    # Execute query
    result = ...
    search_cache.set(cache_key, result)
    return result
```

**4. Connection Pooling**

SQLite uses WAL mode for better concurrency:

```python
conn.execute("PRAGMA journal_mode = WAL;")
```

For PostgreSQL, connection pooling is handled by psycopg2.

### Future Optimizations

- WebSocket support for real-time updates (eliminate polling)
- Redis for distributed caching
- Celery for distributed task queue
- Database sharding for 10M+ subreddits

---

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=subsearch --cov-report=html

# Run specific test file
pytest tests/test_storage.py

# Run specific test
pytest tests/test_storage.py::test_persist_subreddits
```

### Test Structure

```
tests/
├── conftest.py           # Fixtures and configuration
├── test_storage.py       # Database operations
├── test_search.py        # Search engine logic
├── test_web_app.py       # Flask routes
└── test_config.py        # Configuration validation
```

### Writing Tests

Example test:

```python
def test_persist_subreddits(test_db):
    """Test subreddit persistence and deduplication."""
    job_id = "test_job"
    record_run_start(job_id, {}, source="test")

    subs = [
        {"name": "test1", "subscribers": 1000},
        {"name": "test2", "subscribers": 2000},
    ]

    count = persist_subreddits(job_id, subs, source="test")
    assert count == 2

    # Test deduplication
    count = persist_subreddits(job_id, subs, source="test")
    assert count == 2  # Same subs, updated
```

### Integration Tests

Test against live Reddit API (rate limited):

```bash
# Set test credentials
export REDDIT_CLIENT_ID=test_id
export REDDIT_CLIENT_SECRET=test_secret

# Run integration tests
pytest tests/test_integration.py -v
```

---

## Deployment

### Production Deployment Options

#### 1. Traditional Server (Ubuntu)

```bash
# Install system dependencies
sudo apt update
sudo apt install python3.11 python3.11-venv nginx

# Clone and setup
git clone https://github.com/ericrosenberg1/reddit-sub-analyzer.git
cd reddit-sub-analyzer
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with production settings

# Initialize database
python -c "from subsearch.storage import init_db; init_db()"

# Run with systemd
sudo cp deploy/subsearch.service /etc/systemd/system/
sudo systemctl enable subsearch
sudo systemctl start subsearch
```

**Systemd Service File:**

```ini
[Unit]
Description=Sub Search Web Application
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/reddit-sub-analyzer
Environment="PATH=/var/www/reddit-sub-analyzer/.venv/bin"
ExecStart=/var/www/reddit-sub-analyzer/.venv/bin/python -m subsearch.web_app
Restart=always

[Install]
WantedBy=multi-user.target
```

#### 2. Docker Deployment

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN python -c "from subsearch.storage import init_db; init_db()"

EXPOSE 5055
CMD ["python", "-m", "subsearch.web_app"]
```

**Build and Run:**

```bash
docker build -t sub-search .
docker run -d \
  -p 5055:5055 \
  -v $(pwd)/data:/app/data \
  --env-file .env \
  --name sub-search \
  sub-search
```

#### 3. Fly.io Deployment

```bash
# Install Fly CLI
curl -L https://fly.io/install.sh | sh

# Login and launch
fly auth login
fly launch

# Configure secrets
fly secrets set REDDIT_CLIENT_ID=your_id
fly secrets set REDDIT_CLIENT_SECRET=your_secret

# Deploy
fly deploy
```

#### 4. Railway Deployment

1. Fork repository on GitHub
2. Connect Railway to your GitHub account
3. Import the forked repository
4. Add environment variables in Railway dashboard
5. Deploy automatically on push

### PostgreSQL Setup

For production, use PostgreSQL:

```bash
# Install PostgreSQL
sudo apt install postgresql postgresql-contrib

# Create database
sudo -u postgres psql
CREATE DATABASE subsearch;
CREATE USER subsearch_user WITH PASSWORD 'secure_password';
GRANT ALL PRIVILEGES ON DATABASE subsearch TO subsearch_user;

# Configure Sub Search
SUBSEARCH_DB_TYPE=postgres
DB_POSTGRES_HOST=localhost
DB_POSTGRES_PORT=5432
DB_POSTGRES_DB=subsearch
DB_POSTGRES_USER=subsearch_user
DB_POSTGRES_PASSWORD=secure_password
```

### Nginx Configuration

```nginx
server {
    listen 80;
    server_name allthesubs.ericrosenberg.com;

    location / {
        proxy_pass http://127.0.0.1:5055;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SSL configuration (add Let's Encrypt)
    listen 443 ssl;
    ssl_certificate /etc/letsencrypt/live/allthesubs.ericrosenberg.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/allthesubs.ericrosenberg.com/privkey.pem;
}
```

### Monitoring

**Health Check Endpoint:**

```python
@app.route("/health")
def health():
    return jsonify({
        "status": "healthy",
        "version": get_current_build_number(),
        "database": "connected" if check_db() else "error"
    })
```

**Logging:**

```python
# Production logging configuration
import logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s in %(name)s: %(message)s',
    handlers=[
        logging.FileHandler('subsearch.log'),
        logging.StreamHandler()
    ]
)
```

---

## Contributing

### Development Workflow

1. **Fork and Clone**
   ```bash
   git clone https://github.com/YOUR_USERNAME/reddit-sub-analyzer.git
   cd reddit-sub-analyzer
   ```

2. **Create Branch**
   ```bash
   git checkout -b feature/amazing-feature
   ```

3. **Make Changes**
   - Write code
   - Add tests
   - Update documentation

4. **Run Tests**
   ```bash
   pytest
   black subsearch/
   flake8 subsearch/
   ```

5. **Commit**
   ```bash
   git add .
   git commit -m "feat: add amazing feature"
   ```

6. **Push and PR**
   ```bash
   git push origin feature/amazing-feature
   # Open pull request on GitHub
   ```

### Commit Message Convention

Follow semantic commit format:

- `feat: add new feature`
- `fix: resolve bug in search`
- `docs: update API documentation`
- `refactor: improve storage layer`
- `test: add unit tests for config`
- `chore: update dependencies`

### Code Style

- **Black** for formatting (line length 120)
- **Type hints** for function signatures
- **Docstrings** for public APIs
- **Comments** for complex logic

Example:

```python
def search_subreddits(
    *,
    q: Optional[str] = None,
    min_subs: Optional[int] = None,
    page: int = 1,
    page_size: int = 50,
) -> Dict:
    """
    Search subreddits in the database.

    Args:
        q: Keyword to search in subreddit names
        min_subs: Minimum subscriber count filter
        page: Page number for pagination (1-indexed)
        page_size: Number of results per page (1-200)

    Returns:
        Dict containing:
            - total: Total matching subreddits
            - page: Current page number
            - page_size: Results per page
            - rows: List of subreddit dictionaries
    """
```

### Pull Request Guidelines

- Describe what changed and why
- Link related issues
- Include screenshots for UI changes
- Ensure all tests pass
- Update documentation if needed

---

## Troubleshooting

### Common Issues

**Issue: Database locked error**

```
sqlite3.OperationalError: database is locked
```

**Solution:**
- Enable WAL mode (should be automatic)
- Reduce concurrent job limit
- Consider PostgreSQL for high concurrency

**Issue: Reddit API rate limit**

```
prawcore.exceptions.TooManyRequests
```

**Solution:**
- Increase `SUBSEARCH_RATE_LIMIT_DELAY` to 0.2 or higher
- Reduce search frequency
- Use Reddit authenticated credentials for higher limits

**Issue: Jobs stuck in running state**

**Solution:**
- Nightly cleanup will mark stale jobs as failed after 24 hours
- Manual cleanup: `cleanup_stale_runs(max_age_hours=1)`

**Issue: High memory usage**

**Solution:**
- Clear caches periodically
- Reduce `PERSIST_BATCH_SIZE`
- Limit `MAX_CONCURRENT_JOBS`

### Debug Mode

Enable Flask debug mode:

```bash
export FLASK_DEBUG=1
python -m subsearch.web_app
```

**Warning:** Never use debug mode in production!

### Database Inspection

```python
from subsearch.storage import db_conn

with db_conn() as conn:
    # Count total subreddits
    row = conn.execute("SELECT COUNT(*) FROM subreddits").fetchone()
    print(f"Total: {row[0]}")

    # Find stale runs
    rows = conn.execute("""
        SELECT job_id, started_at
        FROM query_runs
        WHERE completed_at IS NULL
    """).fetchall()
    for row in rows:
        print(f"Stale job: {row['job_id']} started {row['started_at']}")
```

### Performance Profiling

```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# Run code to profile
search_subreddits(q="gaming", page_size=1000)

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)
```

---

## Additional Resources

- **GitHub Repository:** https://github.com/ericrosenberg1/reddit-sub-analyzer
- **User Guide:** [HELP.md](HELP.md)
- **API Documentation:** [API.md](API.md)
- **Changelog:** [CHANGELOG.md](CHANGELOG.md)
- **PRAW Documentation:** https://praw.readthedocs.io/
- **Flask Documentation:** https://flask.palletsprojects.com/

---

**Last Updated:** November 2025
**Version:** 2025.11.01.0

*Built with care by the open source community*
