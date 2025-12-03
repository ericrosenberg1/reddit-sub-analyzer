"""
Django context processors for search app.
"""

from django.conf import settings


def site_context(request):
    """Add common context variables to all templates."""
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
        'config_warnings': config_warnings,
        'random_search_interval': settings.RANDOM_SEARCH_INTERVAL,
    }
