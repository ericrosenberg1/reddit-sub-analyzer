"""
Centralized configuration management with safe defaults and validation.

This module handles all environment variable parsing with proper fallbacks
and generates warnings for production deployments with missing configs.
"""

import logging
import os
from typing import List, Optional

logger = logging.getLogger("config")

# Global list of configuration warnings
CONFIG_WARNINGS: List[str] = []


def _warn(message: str) -> None:
    """Add a configuration warning to the global list."""
    CONFIG_WARNINGS.append(message)
    logger.warning(message)


def _get_bool(key: str, default: bool = False) -> bool:
    """Parse boolean environment variable with fallback."""
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(key: str, default: int, min_val: Optional[int] = None, max_val: Optional[int] = None) -> int:
    """Parse integer environment variable with bounds checking."""
    try:
        value = int(os.getenv(key, default) or default)
        if min_val is not None:
            value = max(value, min_val)
        if max_val is not None:
            value = min(value, max_val)
        return value
    except (TypeError, ValueError):
        logger.debug(f"{key} parsing failed, using default {default}")
        return default


def _get_float(key: str, default: float, min_val: Optional[float] = None, max_val: Optional[float] = None) -> float:
    """Parse float environment variable with bounds checking."""
    try:
        value = float(os.getenv(key, default) or default)
        if min_val is not None:
            value = max(value, min_val)
        if max_val is not None:
            value = min(value, max_val)
        return value
    except (TypeError, ValueError):
        logger.debug(f"{key} parsing failed, using default {default}")
        return default


def _get_str(key: str, default: str = "", required: bool = False) -> str:
    """Parse string environment variable with optional requirement check."""
    value = os.getenv(key, "").strip() or default
    if required and not value:
        _warn(f"{key} is required but not set. Application may not function correctly.")
    return value


# Flask Configuration
FLASK_SECRET_KEY = _get_str("FLASK_SECRET_KEY")
if not FLASK_SECRET_KEY:
    _warn("FLASK_SECRET_KEY not set - using insecure default. THIS IS UNSAFE FOR PRODUCTION!")
    FLASK_SECRET_KEY = "dev-only-insecure-key-set-FLASK_SECRET_KEY-in-production"

SITE_URL = _get_str("SITE_URL", "")
PORT = _get_int("PORT", 5055, min_val=1, max_val=65535)

# Reddit API Configuration
REDDIT_CLIENT_ID = _get_str("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = _get_str("REDDIT_CLIENT_SECRET", "")
REDDIT_USERNAME = _get_str("REDDIT_USERNAME", "")
REDDIT_PASSWORD = _get_str("REDDIT_PASSWORD", "")
REDDIT_USER_AGENT = _get_str("REDDIT_USER_AGENT", "SubSearch/1.0 (self-hosted)")
REDDIT_TIMEOUT = _get_int("REDDIT_TIMEOUT", 10, min_val=3, max_val=120)

# Validate Reddit credentials
if not REDDIT_CLIENT_ID:
    _warn("REDDIT_CLIENT_ID not configured - Reddit API calls will fail. Get credentials at reddit.com/prefs/apps")
if not REDDIT_CLIENT_SECRET:
    _warn("REDDIT_CLIENT_SECRET not configured - Reddit API calls will fail. Get credentials at reddit.com/prefs/apps")

# Database Configuration
DB_TYPE = _get_str("DB_TYPE", "sqlite").lower()
if DB_TYPE not in ("sqlite", "postgres"):
    _warn(f"DB_TYPE '{DB_TYPE}' invalid, defaulting to sqlite")
    DB_TYPE = "sqlite"

SUBSEARCH_BASE_DIR = _get_str("SUBSEARCH_BASE_DIR") or os.path.abspath(os.getcwd())
SUBSEARCH_DATA_DIR = _get_str("SUBSEARCH_DATA_DIR") or os.path.join(SUBSEARCH_BASE_DIR, "data")
SUBSEARCH_DB_PATH = _get_str("SUBSEARCH_DB_PATH") or os.path.join(SUBSEARCH_DATA_DIR, "subsearch.db")

# PostgreSQL Configuration
DB_POSTGRES_HOST = _get_str("DB_POSTGRES_HOST", "localhost")
DB_POSTGRES_PORT = _get_int("DB_POSTGRES_PORT", 5432, min_val=1, max_val=65535)
DB_POSTGRES_DB = _get_str("DB_POSTGRES_DB", "subsearch")
DB_POSTGRES_USER = _get_str("DB_POSTGRES_USER", "subsearch")
DB_POSTGRES_PASSWORD = _get_str("DB_POSTGRES_PASSWORD", "")
DB_POSTGRES_SSLMODE = _get_str("DB_POSTGRES_SSLMODE", "prefer")

if DB_TYPE == "postgres" and not DB_POSTGRES_PASSWORD:
    _warn("DB_TYPE is postgres but DB_POSTGRES_PASSWORD is not set")

# Job Queue Configuration
MAX_CONCURRENT_JOBS = _get_int("SUBSEARCH_MAX_CONCURRENT_JOBS", 1, min_val=1, max_val=10)
RATE_LIMIT_DELAY = _get_float("SUBSEARCH_RATE_LIMIT_DELAY", 0.2, min_val=0.1, max_val=5.0)
PUBLIC_API_LIMIT_CAP = _get_int("SUBSEARCH_PUBLIC_API_LIMIT", 2000, min_val=200, max_val=5000)
JOB_TIMEOUT_SECONDS = _get_int("SUBSEARCH_JOB_TIMEOUT_SECONDS", 3600, min_val=60, max_val=86400)
PERSIST_BATCH_SIZE = _get_int("SUBSEARCH_PERSIST_BATCH_SIZE", 32, min_val=5, max_val=256)

# Auto-Ingest Configuration
AUTO_INGEST_ENABLED = _get_bool("AUTO_INGEST_ENABLED", True)
AUTO_INGEST_INTERVAL_MINUTES = _get_int("AUTO_INGEST_INTERVAL_MINUTES", 180, min_val=15, max_val=1440)
AUTO_INGEST_LIMIT = _get_int("AUTO_INGEST_LIMIT", 1000, min_val=100, max_val=5000)
AUTO_INGEST_MIN_SUBS = _get_int("AUTO_INGEST_MIN_SUBS", 0, min_val=0)
AUTO_INGEST_DELAY = _get_float("AUTO_INGEST_DELAY_SEC", 0.25, min_val=0.0, max_val=5.0)
AUTO_INGEST_KEYWORDS = [k.strip() for k in _get_str("AUTO_INGEST_KEYWORDS", "").split(",") if k.strip()]

# Random Search Configuration
RANDOM_SEARCH_ENABLED = _get_bool("RANDOM_SEARCH_ENABLED", True)
RANDOM_SEARCH_INTERVAL_MINUTES = _get_int("RANDOM_SEARCH_INTERVAL_MINUTES", 360, min_val=15, max_val=1440)
RANDOM_SEARCH_LIMIT = _get_int("RANDOM_SEARCH_LIMIT", 2000, min_val=50, max_val=2000)
RANDOM_WORD_API = _get_str("RANDOM_WORD_API", "https://random-word-api.vercel.app/api?words=1")

# Volunteer Node Email Configuration
NODE_EMAIL_SENDER = _get_str("NODE_EMAIL_SENDER", "")
NODE_EMAIL_SENDER_NAME = _get_str("NODE_EMAIL_SENDER_NAME", "Sub Search Nodes")
NODE_EMAIL_SMTP_HOST = _get_str("NODE_EMAIL_SMTP_HOST", "")
NODE_EMAIL_SMTP_PORT = _get_int("NODE_EMAIL_SMTP_PORT", 587, min_val=1, max_val=65535)
NODE_EMAIL_SMTP_USERNAME = _get_str("NODE_EMAIL_SMTP_USERNAME", "")
NODE_EMAIL_SMTP_PASSWORD = _get_str("NODE_EMAIL_SMTP_PASSWORD", "")
NODE_EMAIL_USE_TLS = _get_bool("NODE_EMAIL_USE_TLS", True)
NODE_CLEANUP_INTERVAL_SECONDS = _get_int("NODE_CLEANUP_INTERVAL_SECONDS", 86400, min_val=3600)
NODE_BROKEN_RETENTION_DAYS = _get_int("NODE_BROKEN_RETENTION_DAYS", 7, min_val=1)

# Phone Home Configuration
PHONE_HOME_ENABLED = _get_bool("PHONE_HOME", False)
PHONE_HOME_ENDPOINT = _get_str("PHONE_HOME_ENDPOINT", "https://allthesubs.ericrosenberg.com/api/ingest")
PHONE_HOME_TOKEN = _get_str("PHONE_HOME_TOKEN", "")
PHONE_HOME_TIMEOUT = _get_float("PHONE_HOME_TIMEOUT", 10.0, min_val=1.0, max_val=60.0)
PHONE_HOME_BATCH_MAX = _get_int("PHONE_HOME_BATCH_MAX", 500, min_val=1, max_val=5000)
PHONE_HOME_SOURCE = SITE_URL or _get_str("PHONE_HOME_SOURCE", "self-hosted")

if PHONE_HOME_ENABLED and not PHONE_HOME_TOKEN:
    _warn("PHONE_HOME enabled without PHONE_HOME_TOKEN - sync will be anonymous")


def get_config_warnings() -> List[str]:
    """Return list of configuration warnings for display in UI."""
    return list(CONFIG_WARNINGS)
