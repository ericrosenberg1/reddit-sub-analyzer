# Migration Guide: Redis Queue & PostgreSQL Database

This guide will walk you through migrating from the in-memory queue to Redis, and then from SQLite to PostgreSQL.

## Prerequisites

- Root/sudo access to your server
- Current SQLite database backup
- Server running Ubuntu/Debian (adjust package manager commands for other distros)

---

## Part 1: Migrate to Redis Queue (Recommended First)

Redis provides persistent queue management with priority support and better crash recovery.

### Step 1: Install Redis

```bash
# On Ubuntu/Debian
sudo apt update
sudo apt install redis-server

# Start and enable Redis
sudo systemctl start redis-server
sudo systemctl enable redis-server

# Verify Redis is running
redis-cli ping
# Should return: PONG
```

### Step 2: Install Python Redis Dependencies

```bash
cd /root/reddit-sub-analyzer

# Install Redis Python packages
pip install redis>=5.0
```

### Step 3: Update Environment Variables

Add to your `.env` file:

```bash
# Redis configuration
REDIS_URL=redis://localhost:6379/0
USE_REDIS_QUEUE=true
```

### Step 4: Update Application Code

The Redis queue code is already in your repository (`subsearch/redis_queue.py`), but you need to integrate it into `web_app.py`.

Edit `subsearch/web_app.py` to use Redis queue instead of the in-memory heap queue:

```python
# At the top of the file, add:
import os
USE_REDIS = os.getenv('USE_REDIS_QUEUE', 'false').lower() == 'true'

if USE_REDIS:
    from subsearch.redis_queue import RedisQueue
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    job_queue_backend = RedisQueue(REDIS_URL)
else:
    # Keep existing heap-based queue
    job_queue = []
    job_queue_counter = 0
```

Then replace queue operations:
- `_enqueue_job()` → call `job_queue_backend.enqueue()`
- `heapq.heappop()` → call `job_queue_backend.dequeue()`
- Queue status → call `job_queue_backend.get_queue_status()`

### Step 5: Test Redis Queue

```bash
# Test the priority queue behavior
python3 scripts/test_queue_priority.py

# Should show manual searches (priority 0) before automated (priority 1)
```

### Step 6: Restart Application

```bash
sudo systemctl restart reddit-sub-analyzer

# Check logs
sudo journalctl -u reddit-sub-analyzer -f
```

### Step 7: Verify Queue Persistence

1. Submit a search via the web interface
2. Restart the service: `sudo systemctl restart reddit-sub-analyzer`
3. Check that queued jobs persist after restart

---

## Part 2: Migrate to PostgreSQL Database

PostgreSQL provides better performance, concurrency, and scaling compared to SQLite.

### Step 1: Install PostgreSQL

```bash
# On Ubuntu/Debian
sudo apt update
sudo apt install postgresql postgresql-contrib

# Start and enable PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Verify installation
sudo -u postgres psql --version
```

### Step 2: Create PostgreSQL Database and User

```bash
# Switch to postgres user
sudo -u postgres psql

# Inside psql prompt:
CREATE DATABASE subsearch;
CREATE USER subsearch_user WITH PASSWORD 'YOUR_SECURE_PASSWORD_HERE';
GRANT ALL PRIVILEGES ON DATABASE subsearch TO subsearch_user;

# PostgreSQL 15+ requires additional grants
\c subsearch
GRANT ALL ON SCHEMA public TO subsearch_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO subsearch_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO subsearch_user;

# Exit psql
\q
```

### Step 3: Backup Current SQLite Database

```bash
cd /root/reddit-sub-analyzer

# Create backup directory
mkdir -p backups

# Backup SQLite database
cp subsearch/data/subsearch.db backups/subsearch_$(date +%Y%m%d_%H%M%S).db

# Verify backup
ls -lh backups/
```

### Step 4: Install PostgreSQL Python Dependencies

```bash
# Install from requirements file
pip install psycopg2-binary>=2.9
```

Or uncomment the line in `requirements.txt` and run:
```bash
pip install -r requirements.txt
```

### Step 5: Set PostgreSQL Environment Variables

Add to your `.env` file:

```bash
# Database configuration
DB_TYPE=postgres
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=subsearch
POSTGRES_USER=subsearch_user
POSTGRES_PASSWORD=YOUR_SECURE_PASSWORD_HERE
```

### Step 6: Run Migration Script

```bash
cd /root/reddit-sub-analyzer

# Set environment variables for migration
export POSTGRES_DB=subsearch
export POSTGRES_USER=subsearch_user
export POSTGRES_PASSWORD=YOUR_SECURE_PASSWORD_HERE

# Run migration (will prompt for confirmation)
python3 scripts/migrate_sqlite_to_postgres.py
```

The script will:
1. Connect to both databases
2. Create PostgreSQL schema
3. Migrate data in batches
4. Verify row counts match

Example output:
```
============================================================
SQLite to PostgreSQL Migration
============================================================

SQLite database: subsearch/data/subsearch.db
PostgreSQL target: subsearch_user@localhost:5432/subsearch

⚠️  WARNING: This will DROP all existing tables in PostgreSQL!
Continue? (yes/no): yes

Connecting to databases...
✓ Connected to both databases
Creating PostgreSQL schema...
✓ PostgreSQL schema created

Migrating table: subreddits
  Total rows to migrate: 3458291
  ✓ Migrated 3458291/3458291 rows successfully

Migrating table: query_runs
  Total rows to migrate: 1823
  ✓ Migrated 1823/1823 rows successfully

Migrating table: volunteer_nodes
  Total rows to migrate: 5
  ✓ Migrated 5/5 rows successfully

Verifying migration...
  ✓ subreddits: SQLite=3458291, PostgreSQL=3458291
  ✓ query_runs: SQLite=1823, PostgreSQL=1823
  ✓ volunteer_nodes: SQLite=5, PostgreSQL=5

✓ Migration verified successfully!
```

### Step 7: Update Application to Use PostgreSQL

The application should automatically use PostgreSQL when `DB_TYPE=postgres` is set in `.env`.

Verify in `subsearch/storage.py` that it detects the correct database type.

### Step 8: Restart Application

```bash
sudo systemctl restart reddit-sub-analyzer

# Watch logs for any errors
sudo journalctl -u reddit-sub-analyzer -f
```

### Step 9: Verify PostgreSQL Migration

1. Access your application web interface
2. Check that "All The Subs" shows all existing subreddits
3. Run a new search to verify data is being written to PostgreSQL
4. Check PostgreSQL directly:

```bash
sudo -u postgres psql -d subsearch -c "SELECT COUNT(*) FROM subreddits;"
sudo -u postgres psql -d subsearch -c "SELECT COUNT(*) FROM query_runs;"
```

### Step 10: Optimize PostgreSQL (Optional)

```bash
sudo -u postgres psql -d subsearch

-- Update statistics
ANALYZE;

-- Reindex for better performance
REINDEX DATABASE subsearch;

-- Vacuum to reclaim space
VACUUM ANALYZE;

\q
```

---

## Troubleshooting

### Redis Connection Issues

```bash
# Check Redis is running
sudo systemctl status redis-server

# Check Redis logs
sudo journalctl -u redis-server -f

# Test connection
redis-cli ping
```

### PostgreSQL Connection Issues

```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Check PostgreSQL logs
sudo tail -f /var/log/postgresql/postgresql-*-main.log

# Test connection
sudo -u postgres psql -d subsearch -c "SELECT version();"
```

### Migration Verification Failed

If row counts don't match:

```bash
# Check SQLite counts
sqlite3 subsearch/data/subsearch.db "SELECT COUNT(*) FROM subreddits;"

# Check PostgreSQL counts
sudo -u postgres psql -d subsearch -c "SELECT COUNT(*) FROM subreddits;"

# Re-run migration with fresh database
sudo -u postgres psql -d subsearch -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
python3 scripts/migrate_sqlite_to_postgres.py
```

### Application Won't Start

```bash
# Check application logs
sudo journalctl -u reddit-sub-analyzer -n 100 --no-pager

# Verify environment variables
cat /root/reddit-sub-analyzer/.env | grep -E '(DB_TYPE|POSTGRES|REDIS)'

# Test database connection manually
python3 -c "
import os
os.environ['DB_TYPE'] = 'postgres'
os.environ['POSTGRES_DB'] = 'subsearch'
os.environ['POSTGRES_USER'] = 'subsearch_user'
os.environ['POSTGRES_PASSWORD'] = 'YOUR_PASSWORD'
from subsearch.storage import get_db_connection
conn = get_db_connection()
print('Connection successful!')
conn.close()
"
```

---

## Rollback Procedures

### Rollback Redis Queue (revert to in-memory)

1. Edit `.env`: Set `USE_REDIS_QUEUE=false` or remove the line
2. Restart: `sudo systemctl restart reddit-sub-analyzer`

### Rollback PostgreSQL (revert to SQLite)

1. Edit `.env`: Set `DB_TYPE=sqlite` or remove the line
2. Ensure SQLite backup exists: `ls -lh backups/`
3. Restore if needed: `cp backups/subsearch_TIMESTAMP.db subsearch/data/subsearch.db`
4. Restart: `sudo systemctl restart reddit-sub-analyzer`

---

## Performance Monitoring

### Redis Monitoring

```bash
# View Redis stats
redis-cli INFO stats

# Monitor commands in real-time
redis-cli MONITOR

# Check queue size
redis-cli ZCARD subsearch:queue
```

### PostgreSQL Monitoring

```bash
# View active connections
sudo -u postgres psql -d subsearch -c "SELECT count(*) FROM pg_stat_activity;"

# View table sizes
sudo -u postgres psql -d subsearch -c "
SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"

# View slow queries (requires pg_stat_statements extension)
sudo -u postgres psql -d subsearch -c "SELECT query, calls, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;"
```

---

## Next Steps After Migration

1. **Monitor Performance**: Watch logs and response times for 24-48 hours
2. **Backup Strategy**: Set up automated PostgreSQL backups using `pg_dump`
3. **Tune PostgreSQL**: Adjust `postgresql.conf` for your server's RAM
4. **Archive SQLite**: Once confident, archive the SQLite backup offsite
5. **Document**: Update your deployment docs with new database info

---

## Need Help?

- Check application logs: `sudo journalctl -u reddit-sub-analyzer -f`
- Test queue: `python3 scripts/test_queue_priority.py`
- GitHub issues: https://github.com/ericrosenberg1/reddit-sub-analyzer/issues
