"""
Django context processors for search app.
"""

from django.conf import settings
from pathlib import Path


def site_context(request):
    """Add common context variables to all templates."""
    version_file = Path(settings.BASE_DIR) / 'VERSION'
    try:
        version = version_file.read_text().strip()
    except Exception:
        version = 'dev'

    # Config warnings
    config_warnings = []
    if not settings.REDDIT_CLIENT_ID:
        config_warnings.append("REDDIT_CLIENT_ID not configured - Reddit API calls will fail.")
    if not settings.REDDIT_CLIENT_SECRET:
        config_warnings.append("REDDIT_CLIENT_SECRET not configured - Reddit API calls will fail.")
    if settings.SECRET_KEY.startswith('dev-only'):
        config_warnings.append("SECRET_KEY not set - using insecure default. THIS IS UNSAFE FOR PRODUCTION!")

    return {
        'site_url': settings.SITE_URL,
        'build_number': version,
        'config_warnings': config_warnings,
        'random_search_interval': settings.RANDOM_SEARCH_INTERVAL,
    }
