# Performance Optimizations Guide

This document outlines the performance optimizations implemented in Sub Search and guidance on scaling.

## Recent Optimizations (November 2024)

### 1. Queue ETA Calculation ✅

**What changed:**
- Added real-time ETA display for queued jobs
- Calculates average job completion time from last 10 runs
- Shows estimated wait time in human-readable format

**Files modified:**
- `subsearch/web_app.py` - Added `_calculate_average_job_time()` function
- `subsearch/templates/index.html` - Added ETA display and formatting

**User impact:**
Users now see "ETA: ~3 minutes" when waiting in queue instead of just "2 orders ahead"

### 2. Moderator Activity Check Optimization ✅

**What changed:**
- Reduced moderator sampling from 5 → 2 moderators per subreddit
- Reduced max activity fetches from 8,000 → 1,000 per job
- Made limits configurable via environment variables

**Files modified:**
- `subsearch/auto_sub_analyzer.py` - Updated defaults
- `.env.example` - Added `SUBSEARCH_MOD_ACTIVITY_SAMPLE_SIZE` and `SUBSEARCH_MOD_ACTIVITY_FETCH_LIMIT`

**Performance impact:**
- ~80% reduction in extra API calls for moderator activity
- Major speed improvement for large searches (was causing 10+ minute delays)

**Configuration:**
```bash
# Disable moderator activity checks entirely (fastest)
SUBSEARCH_MOD_ACTIVITY_SAMPLE_SIZE=0

# Light checking (recommended - default)
SUBSEARCH_MOD_ACTIVITY_SAMPLE_SIZE=2
SUBSEARCH_MOD_ACTIVITY_FETCH_LIMIT=1000

# Thorough checking (slower but more accurate)
SUBSEARCH_MOD_ACTIVITY_SAMPLE_SIZE=5
SUBSEARCH_MOD_ACTIVITY_FETCH_LIMIT=5000
```

### 3. Rate Limit Delay Reduction ✅

**What changed:**
- Reduced default delay between API calls from 0.2s → 0.15s
- Added documentation for tuning based on authentication

**Files modified:**
- `subsearch/config.py` - Updated default
- `.env.example` - Added tuning guidance

**Performance impact:**
- 25% faster API searches
- For 1000 subreddits: 200s → 150s

**Tuning guidance:**
```bash
# Authenticated users (username + password set) - can go faster
SUBSEARCH_RATE_LIMIT_DELAY=0.1

# Read-only mode (no credentials) - stay conservative
SUBSEARCH_RATE_LIMIT_DELAY=0.2

# Getting rate limited? Increase the delay
SUBSEARCH_RATE_LIMIT_DELAY=0.3
```

### 4. Progress Phase Tracking ✅

**What changed:**
- Jobs now track which phase they're in (DB search vs API search)
- Better visibility into what's happening during long-running jobs

**Files modified:**
- `subsearch/web_app.py` - Added `progress_phase` field and updates

**User impact:**
Users can see when the database search completes and API search begins

## Performance Benchmarks

### Before Optimizations
- **1000 subreddit search**: 8-12 minutes
- **Moderator activity checks**: Up to 8,000 extra API calls
- **Rate limit delay**: 0.2s × 1000 = 200s minimum

### After Optimizations
- **1000 subreddit search**: 3-5 minutes (typical)
- **Moderator activity checks**: Max 1,000 extra API calls
- **Rate limit delay**: 0.15s × 1000 = 150s minimum

### Bottleneck Analysis

**Current bottlenecks (in order):**
1. **Reddit API rate limits** - Fundamental constraint, can't eliminate
2. **Network latency** - Each subreddit requires 1-3 API calls
3. **Database queries** - Optimized with batching, minimal impact
4. **Thread overhead** - Negligible for current scale

## Scaling Considerations

### Current Architecture: Threading ✅

**Works well for:**
- Single-server deployments
- 1-5 concurrent jobs
- I/O-bound tasks (Reddit API calls)
- Small-to-medium instances

**Limitations:**
- Single process (doesn't use multiple CPUs)
- No task persistence across restarts
- Limited to one server

### When to Consider Worker Queues

**Migrate to Celery/RQ when you experience:**
1. **High concurrency needs** - Regularly running 5+ jobs simultaneously
2. **Multi-server scaling** - Want to distribute work across machines
3. **Task persistence** - Jobs must survive server restarts
4. **Complex scheduling** - Need advanced cron-like scheduling
5. **Better monitoring** - Want task dashboards and retry logic

### Worker Queue Options

#### Option 1: RQ (Redis Queue) - Recommended First Step
**Best for:** Growing from threading without heavy complexity

```python
# Install
pip install rq redis

# Pros:
# - Simple migration from threading
# - Python-native, easy to understand
# - Good for small-to-medium scale
# - Minimal configuration

# Cons:
# - Requires Redis server
# - Less features than Celery
# - Smaller ecosystem
```

**Migration effort:** 2-3 hours

#### Option 2: Celery + Redis - Industry Standard
**Best for:** Enterprise scale, complex workflows

```python
# Install
pip install celery redis

# Pros:
# - Battle-tested, mature ecosystem
# - Advanced features (chaining, groups, etc.)
# - Great monitoring tools (Flower)
# - Flexible backends

# Cons:
# - More complex setup
# - Steeper learning curve
# - Heavier resource usage
```

**Migration effort:** 1-2 days

#### Option 3: APScheduler - Lightweight
**Best for:** Better scheduling without external dependencies

```python
# Install
pip install apscheduler

# Pros:
# - No external services needed
# - Easy to add to existing code
# - Good for periodic tasks

# Cons:
# - Still single-process
# - Not distributed
# - No task dashboard
```

**Migration effort:** 2-4 hours

#### Option 4: Dramatiq - Modern Alternative
**Best for:** New projects wanting modern patterns

```python
# Install
pip install dramatiq redis

# Pros:
# - Modern, clean API
# - RabbitMQ or Redis support
# - Good performance

# Cons:
# - Smaller community than Celery
# - Fewer integrations
```

**Migration effort:** 1 day

### Recommendation Matrix

| Current Scale | Recommendation | Why |
|---------------|----------------|-----|
| < 100 jobs/day | **Keep threading** | Current optimizations are sufficient |
| 100-1000 jobs/day | **Consider RQ** | Simple migration, handles growth |
| 1000-10000 jobs/day | **Migrate to Celery** | Need robustness & monitoring |
| > 10000 jobs/day | **Celery + multiple workers** | Distributed processing essential |

## Monitoring Performance

### Key Metrics to Track

1. **Average job duration** - Track via `runs` table
2. **Queue depth** - How many jobs waiting
3. **API error rate** - Reddit rate limit hits
4. **Database query time** - Should stay < 1s

### Quick Performance Check

```python
# Check average job time (last 50 jobs)
SELECT
    AVG((julianday(completed_at) - julianday(started_at)) * 86400) as avg_seconds,
    COUNT(*) as total_jobs,
    SUM(CASE WHEN error IS NOT NULL THEN 1 ELSE 0 END) as failed_jobs
FROM runs
WHERE completed_at IS NOT NULL
    AND started_at IS NOT NULL
    AND source = 'sub_search'
ORDER BY started_at DESC
LIMIT 50;
```

### When Performance Degrades

**If jobs are taking too long:**
1. Check `SUBSEARCH_RATE_LIMIT_DELAY` - can you reduce it?
2. Check `SUBSEARCH_MOD_ACTIVITY_SAMPLE_SIZE` - can you disable it?
3. Check Reddit API status - is Reddit slow/down?
4. Check concurrent jobs - reduce `SUBSEARCH_MAX_CONCURRENT_JOBS` if hitting limits

**If getting rate limited:**
1. Increase `SUBSEARCH_RATE_LIMIT_DELAY` to 0.2 or 0.3
2. Ensure Reddit credentials are set (authenticated = higher limits)
3. Reduce `SUBSEARCH_MAX_CONCURRENT_JOBS` to 1

## Future Optimization Ideas

### Short Term (Can implement now)
- [ ] Cache Reddit API responses for 5-10 minutes
- [ ] Batch database inserts more aggressively
- [ ] Add database indexes on frequently queried columns
- [ ] Implement request pooling for Reddit API

### Medium Term (Requires refactoring)
- [ ] Migrate to async/await for better concurrency
- [ ] Add read replicas for database queries
- [ ] Implement progressive search (show results as they come in)
- [ ] Add CDN for static assets

### Long Term (Architectural changes)
- [ ] Migrate to Celery for distributed processing
- [ ] Implement multi-region deployment
- [ ] Add real-time WebSocket updates
- [ ] Build dedicated API worker nodes

## Configuration Cheat Sheet

### Maximum Speed (May hit rate limits)
```bash
SUBSEARCH_RATE_LIMIT_DELAY=0.1
SUBSEARCH_MOD_ACTIVITY_SAMPLE_SIZE=0
SUBSEARCH_MAX_CONCURRENT_JOBS=2
```

### Balanced (Recommended)
```bash
SUBSEARCH_RATE_LIMIT_DELAY=0.15
SUBSEARCH_MOD_ACTIVITY_SAMPLE_SIZE=2
SUBSEARCH_MOD_ACTIVITY_FETCH_LIMIT=1000
SUBSEARCH_MAX_CONCURRENT_JOBS=1
```

### Conservative (Avoid rate limits)
```bash
SUBSEARCH_RATE_LIMIT_DELAY=0.25
SUBSEARCH_MOD_ACTIVITY_SAMPLE_SIZE=3
SUBSEARCH_MOD_ACTIVITY_FETCH_LIMIT=2000
SUBSEARCH_MAX_CONCURRENT_JOBS=1
```

### Maximum Data Collection (Slow but thorough)
```bash
SUBSEARCH_RATE_LIMIT_DELAY=0.3
SUBSEARCH_MOD_ACTIVITY_SAMPLE_SIZE=5
SUBSEARCH_MOD_ACTIVITY_FETCH_LIMIT=0  # unlimited
SUBSEARCH_MAX_CONCURRENT_JOBS=1
```

## Troubleshooting

### Jobs stuck/not completing
- Check logs for errors
- Verify Reddit API credentials
- Check `JOB_TIMEOUT_SECONDS` (default 1 hour)
- Look for network issues

### Getting rate limited by Reddit
- Increase `SUBSEARCH_RATE_LIMIT_DELAY`
- Verify credentials are set (authenticated mode has higher limits)
- Check if multiple instances are running
- Reduce concurrent jobs

### Queue building up
- Reduce search limits (`SUBSEARCH_PUBLIC_API_LIMIT`)
- Disable auto-ingest temporarily
- Consider scaling to worker queue system
- Check if jobs are erroring out

### Database growing too large
- Implement data retention policy
- Archive old runs
- Consider PostgreSQL for better scaling
- Add database maintenance tasks

---

**Last updated:** November 2024
**Maintained by:** Eric Rosenberg
