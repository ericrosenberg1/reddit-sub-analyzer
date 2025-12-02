"""
Celery configuration for Reddit Sub Analyzer.

Uses Redis as the broker with fallback to memory broker for development.
Implements task priority queuing where user searches get priority 0 (highest)
and automated searches get priority 1 (lower).
"""

import os
from celery import Celery
from django.conf import settings

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'reddit_analyzer.settings')

# Redis URL from environment, fallback to memory broker
REDIS_URL = os.environ.get('REDIS_URL', os.environ.get('CELERY_BROKER_URL', ''))


def get_broker_url():
    """Get the broker URL, falling back to memory if Redis is not available."""
    if REDIS_URL:
        return REDIS_URL
    # Try to connect to default Redis
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, socket_timeout=1)
        r.ping()
        return 'redis://localhost:6379/0'
    except Exception:
        pass
    # Fallback to memory broker (not recommended for production)
    return 'memory://'


def get_result_backend():
    """Get the result backend, using Redis if available or Django DB."""
    if REDIS_URL:
        return REDIS_URL
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, socket_timeout=1)
        r.ping()
        return 'redis://localhost:6379/0'
    except Exception:
        pass
    # Fallback to Django database backend
    return 'django-db'


app = Celery('reddit_analyzer')

# Configure Celery
app.config_from_object('django.conf:settings', namespace='CELERY')

# Override broker and backend with our detection logic
broker_url = get_broker_url()
result_backend = get_result_backend()

app.conf.update(
    broker_url=broker_url,
    result_backend=result_backend,

    # Task priority settings
    task_default_priority=5,
    task_queue_max_priority=10,
    broker_transport_options={
        'priority_steps': list(range(10)),
        'sep': ':',
        'queue_order_strategy': 'priority',
    },

    # Task routing - all search tasks go to 'search' queue
    task_routes={
        'search.tasks.run_sub_search': {'queue': 'search'},
        'search.tasks.run_auto_ingest': {'queue': 'search'},
        'search.tasks.run_random_search': {'queue': 'search'},
        'search.tasks.cleanup_stale_jobs': {'queue': 'cleanup'},
        'search.tasks.cleanup_broken_nodes': {'queue': 'cleanup'},
    },

    # Concurrency settings
    worker_concurrency=1,  # Only one search at a time per worker
    worker_prefetch_multiplier=1,

    # Task execution settings
    task_acks_late=True,  # Acknowledge after completion for reliability
    task_reject_on_worker_lost=True,
    task_time_limit=3600,  # 1 hour max per task
    task_soft_time_limit=3300,  # Soft limit 55 min to allow cleanup

    # Result settings
    result_expires=86400,  # Results expire after 24 hours

    # Serialization
    accept_content=['json'],
    task_serializer='json',
    result_serializer='json',

    # Timezone
    timezone='UTC',
    enable_utc=True,
)

# Auto-discover tasks from all installed apps
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for testing Celery connectivity."""
    print(f'Request: {self.request!r}')
