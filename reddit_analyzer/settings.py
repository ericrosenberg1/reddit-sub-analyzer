"""
Django settings for Reddit Sub Analyzer.

Supports fallback configuration:
- PostgreSQL → SQLite (if PostgreSQL credentials missing)
- Redis → Memory broker (if Redis unavailable)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.environ.get('DEBUG', '0').lower() in ('1', 'true', 'yes')

# Quick-start development settings - unsuitable for production
# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    if DEBUG:
        # Generate a temporary key for development only
        import secrets
        SECRET_KEY = secrets.token_hex(32)
        import warnings
        warnings.warn("DJANGO_SECRET_KEY not set - using random key for development. Set it in production!")
    else:
        raise ValueError(
            "DJANGO_SECRET_KEY must be set in production. "
            "Generate one with: python -c 'import secrets; print(secrets.token_hex(32))'"
        )

ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
ALLOWED_HOSTS = [h.strip() for h in ALLOWED_HOSTS if h.strip()]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party apps
    'django_celery_results',
    'django_celery_beat',

    # Local apps
    'search',
    'nodes',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'reddit_analyzer.middleware.RateLimitMiddleware',
    'reddit_analyzer.middleware.SecurityHeadersMiddleware',
    'reddit_analyzer.middleware.ErrorReportingMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'reddit_analyzer.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'search.context_processors.site_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'reddit_analyzer.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

def get_database_config():
    """
    Get database configuration with PostgreSQL → SQLite fallback.
    """
    db_type = os.environ.get('DB_TYPE', 'sqlite').lower()

    if db_type == 'postgres':
        # Check if PostgreSQL credentials are available
        pg_host = os.environ.get('DB_POSTGRES_HOST', 'localhost')
        pg_port = os.environ.get('DB_POSTGRES_PORT', '5432')
        pg_db = os.environ.get('DB_POSTGRES_DB', 'subsearch')
        pg_user = os.environ.get('DB_POSTGRES_USER', 'subsearch')
        pg_password = os.environ.get('DB_POSTGRES_PASSWORD', '')

        if pg_password:
            # PostgreSQL is configured
            try:
                import psycopg2
                return {
                    'ENGINE': 'django.db.backends.postgresql',
                    'NAME': pg_db,
                    'USER': pg_user,
                    'PASSWORD': pg_password,
                    'HOST': pg_host,
                    'PORT': pg_port,
                    'OPTIONS': {
                        'sslmode': os.environ.get('DB_POSTGRES_SSLMODE', 'prefer'),
                    },
                    'CONN_MAX_AGE': 60,
                }
            except ImportError:
                import warnings
                warnings.warn("psycopg2 not installed, falling back to SQLite")

    # Default to SQLite
    data_dir = os.environ.get('SUBSEARCH_DATA_DIR', '') or str(BASE_DIR / 'data')
    if data_dir:
        os.makedirs(data_dir, exist_ok=True)
    db_path = os.environ.get('SUBSEARCH_DB_PATH', '') or os.path.join(data_dir, 'subsearch.db')

    return {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': db_path,
        'OPTIONS': {
            'timeout': 30,
        },
    }


DATABASES = {
    'default': get_database_config()
}


# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]


# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'subsearch' / 'static',
]
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# =============================================================================
# Redis Configuration (with fallback)
# =============================================================================

def get_redis_url():
    """Get Redis URL if available, otherwise return None."""
    redis_url = os.environ.get('REDIS_URL', '')
    if redis_url:
        return redis_url

    # Try to connect to default Redis
    try:
        import redis
        r = redis.Redis(host='localhost', port=6379, socket_timeout=1)
        r.ping()
        return 'redis://localhost:6379/0'
    except Exception:
        return None


REDIS_URL = get_redis_url()


# =============================================================================
# Celery Configuration
# =============================================================================

# Broker configuration
if REDIS_URL:
    CELERY_BROKER_URL = REDIS_URL
    CELERY_RESULT_BACKEND = REDIS_URL
else:
    # Fallback to memory broker (development only)
    CELERY_BROKER_URL = 'memory://'
    CELERY_RESULT_BACKEND = 'django-db'

# Task settings
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = 'UTC'
CELERY_ENABLE_UTC = True

# Priority queue settings
CELERY_TASK_DEFAULT_PRIORITY = 5
CELERY_TASK_QUEUE_MAX_PRIORITY = 10
CELERY_BROKER_TRANSPORT_OPTIONS = {
    'priority_steps': list(range(10)),
    'sep': ':',
    'queue_order_strategy': 'priority',
}

# Worker settings
CELERY_WORKER_CONCURRENCY = 1  # Only one search at a time
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True

# Time limits
CELERY_TASK_TIME_LIMIT = int(os.environ.get('SUBSEARCH_JOB_TIMEOUT_SECONDS', 3600))
CELERY_TASK_SOFT_TIME_LIMIT = CELERY_TASK_TIME_LIMIT - 300  # 5 min before hard limit

# Results
CELERY_RESULT_EXPIRES = 86400  # 24 hours


# =============================================================================
# Celery Beat Schedule
# =============================================================================

from celery.schedules import crontab

# Parse interval settings
AUTO_INGEST_ENABLED = os.environ.get('AUTO_INGEST_ENABLED', '1').lower() in ('1', 'true', 'yes')
AUTO_INGEST_INTERVAL = int(os.environ.get('AUTO_INGEST_INTERVAL_MINUTES', 180))
RANDOM_SEARCH_ENABLED = os.environ.get('RANDOM_SEARCH_ENABLED', '1').lower() in ('1', 'true', 'yes')
RANDOM_SEARCH_INTERVAL = int(os.environ.get('RANDOM_SEARCH_INTERVAL_MINUTES', 360))

CELERY_BEAT_SCHEDULE = {}

if RANDOM_SEARCH_ENABLED:
    CELERY_BEAT_SCHEDULE['random-search'] = {
        'task': 'search.tasks.run_random_search',
        'schedule': RANDOM_SEARCH_INTERVAL * 60,  # Convert to seconds
        'options': {'priority': 9},  # Lower priority (higher number = lower priority)
    }

if AUTO_INGEST_ENABLED:
    CELERY_BEAT_SCHEDULE['auto-ingest'] = {
        'task': 'search.tasks.run_auto_ingest',
        'schedule': AUTO_INGEST_INTERVAL * 60,
        'options': {'priority': 9},
    }

# Cleanup tasks - run frequently
CELERY_BEAT_SCHEDULE['cleanup-stale-jobs'] = {
    'task': 'search.tasks.cleanup_stale_jobs',
    'schedule': 300,  # Every 5 minutes
}

CELERY_BEAT_SCHEDULE['cleanup-broken-nodes'] = {
    'task': 'search.tasks.cleanup_broken_nodes',
    'schedule': crontab(hour=3, minute=0),  # Daily at 3 AM
}


# =============================================================================
# Application-Specific Settings
# =============================================================================

# Site configuration
SITE_URL = os.environ.get('SITE_URL', '')

# Reddit API Configuration
REDDIT_CLIENT_ID = os.environ.get('REDDIT_CLIENT_ID', '')
REDDIT_CLIENT_SECRET = os.environ.get('REDDIT_CLIENT_SECRET', '')
REDDIT_USERNAME = os.environ.get('REDDIT_USERNAME', '')
REDDIT_PASSWORD = os.environ.get('REDDIT_PASSWORD', '')
REDDIT_USER_AGENT = os.environ.get('REDDIT_USER_AGENT', 'SubSearch/1.0 (self-hosted)')
REDDIT_TIMEOUT = int(os.environ.get('REDDIT_TIMEOUT', 10))

# Job Queue Configuration
MAX_CONCURRENT_JOBS = int(os.environ.get('SUBSEARCH_MAX_CONCURRENT_JOBS', 1))
RATE_LIMIT_DELAY = float(os.environ.get('SUBSEARCH_RATE_LIMIT_DELAY', 0.15))
PUBLIC_API_LIMIT_CAP = int(os.environ.get('SUBSEARCH_PUBLIC_API_LIMIT', 2000))
JOB_TIMEOUT_SECONDS = int(os.environ.get('SUBSEARCH_JOB_TIMEOUT_SECONDS', 3600))
PERSIST_BATCH_SIZE = int(os.environ.get('SUBSEARCH_PERSIST_BATCH_SIZE', 32))

# Auto-Ingest Configuration
AUTO_INGEST_LIMIT = int(os.environ.get('AUTO_INGEST_LIMIT', 1000))
AUTO_INGEST_MIN_SUBS = int(os.environ.get('AUTO_INGEST_MIN_SUBS', 0))
AUTO_INGEST_DELAY = float(os.environ.get('AUTO_INGEST_DELAY_SEC', 0.25))
AUTO_INGEST_KEYWORDS = [k.strip() for k in os.environ.get('AUTO_INGEST_KEYWORDS', '').split(',') if k.strip()]

# Random Search Configuration
RANDOM_SEARCH_LIMIT = int(os.environ.get('RANDOM_SEARCH_LIMIT', 2000))
RANDOM_WORD_API = os.environ.get('RANDOM_WORD_API', 'https://random-word-api.vercel.app/api?words=1')

# Volunteer Node Configuration
NODE_EMAIL_SENDER = os.environ.get('NODE_EMAIL_SENDER', '')
NODE_EMAIL_SENDER_NAME = os.environ.get('NODE_EMAIL_SENDER_NAME', 'Sub Search Nodes')
NODE_EMAIL_SMTP_HOST = os.environ.get('NODE_EMAIL_SMTP_HOST', '')
NODE_EMAIL_SMTP_PORT = int(os.environ.get('NODE_EMAIL_SMTP_PORT', 587))
NODE_EMAIL_SMTP_USERNAME = os.environ.get('NODE_EMAIL_SMTP_USERNAME', '')
NODE_EMAIL_SMTP_PASSWORD = os.environ.get('NODE_EMAIL_SMTP_PASSWORD', '')
NODE_EMAIL_USE_TLS = os.environ.get('NODE_EMAIL_USE_TLS', '1').lower() in ('1', 'true', 'yes')
NODE_CLEANUP_INTERVAL_SECONDS = int(os.environ.get('NODE_CLEANUP_INTERVAL_SECONDS', 86400))
NODE_BROKEN_RETENTION_DAYS = int(os.environ.get('NODE_BROKEN_RETENTION_DAYS', 7))

# Phone Home Configuration
PHONE_HOME_ENABLED = os.environ.get('PHONE_HOME', 'false').lower() in ('1', 'true', 'yes')
PHONE_HOME_ENDPOINT = os.environ.get('PHONE_HOME_ENDPOINT', 'https://allthesubs.ericrosenberg.com/api/ingest')
PHONE_HOME_TOKEN = os.environ.get('PHONE_HOME_TOKEN', '')
PHONE_HOME_TIMEOUT = float(os.environ.get('PHONE_HOME_TIMEOUT', 10.0))
PHONE_HOME_BATCH_MAX = int(os.environ.get('PHONE_HOME_BATCH_MAX', 500))
PHONE_HOME_SOURCE = SITE_URL or os.environ.get('PHONE_HOME_SOURCE', 'self-hosted')

# Job cleanup settings (shorter than before to fix stuck job issues)
JOB_STALE_THRESHOLD_MINUTES = int(os.environ.get('JOB_STALE_THRESHOLD_MINUTES', 30))  # Reduced from 120

# GitHub Issue Creation for 5xx Errors
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
GITHUB_REPO = os.environ.get('GITHUB_REPO', 'ericrosenberg1/reddit-sub-analyzer')
GITHUB_ISSUE_ENABLED = os.environ.get('GITHUB_ISSUE_ENABLED', 'false').lower() in ('1', 'true', 'yes')


# =============================================================================
# Caching Configuration
# =============================================================================

if REDIS_URL:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': REDIS_URL,
            'OPTIONS': {
                'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            },
            'KEY_PREFIX': 'subsearch',
            'TIMEOUT': 300,  # 5 minutes default
        }
    }
else:
    # Fallback to local memory cache
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'unique-subsearch',
            'TIMEOUT': 300,
        }
    }

# Cache timeouts for different data types
CACHE_TIMEOUT_STATS = 60  # 1 minute for stats
CACHE_TIMEOUT_SUBREDDITS = 300  # 5 minutes for subreddit queries
CACHE_TIMEOUT_JOBS = 30  # 30 seconds for job status


# =============================================================================
# Security Settings
# =============================================================================

# CSRF settings
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_HTTPONLY = True
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h not in ('localhost', '127.0.0.1')]
if DEBUG:
    CSRF_TRUSTED_ORIGINS.extend(['http://localhost:8000', 'http://127.0.0.1:8000'])

# Session settings
SESSION_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'

# HSTS (only in production)
if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.environ.get('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'search': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
    },
}
