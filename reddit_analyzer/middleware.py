"""
Custom middleware for Reddit Sub Analyzer.

Provides:
- Rate limiting for API endpoints and search submissions
- Automatic GitHub issue creation for 5xx errors
- Security headers
- Request logging
"""

import hashlib
import json
import logging
import time
import traceback
from collections import defaultdict
from datetime import datetime, timedelta
from functools import lru_cache
from threading import Lock

import requests
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse, HttpResponseForbidden
from django.utils import timezone

logger = logging.getLogger(__name__)


# =============================================================================
# Rate Limiting Middleware
# =============================================================================

class RateLimitMiddleware:
    """
    Rate limiting middleware for search submissions and API endpoints.

    Limits:
    - Search submissions: 10 per minute per IP
    - API endpoints: 60 per minute per IP
    - Global: 100 requests per minute per IP
    """

    # In-memory storage for rate limiting (use Redis in production)
    _rate_limits = defaultdict(list)
    _lock = Lock()

    # Rate limit configurations
    RATE_LIMITS = {
        'search_submit': {'requests': 10, 'window': 60, 'paths': ['/']},
        'api': {'requests': 60, 'window': 60, 'paths': ['/api/', '/status/', '/stop/']},
        'global': {'requests': 100, 'window': 60, 'paths': None},
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip rate limiting for static files and admin
        if request.path.startswith(('/static/', '/admin/')):
            return self.get_response(request)

        client_ip = self._get_client_ip(request)

        # Check rate limits
        if request.method == 'POST' and request.path == '/':
            # Search submission - stricter limit
            if not self._check_rate_limit(client_ip, 'search_submit'):
                logger.warning("Rate limit exceeded for search submission from %s", client_ip)
                return JsonResponse({
                    'error': 'Rate limit exceeded. Please wait before submitting another search.',
                    'retry_after': 60,
                }, status=429)

        if any(request.path.startswith(p) for p in self.RATE_LIMITS['api']['paths']):
            if not self._check_rate_limit(client_ip, 'api'):
                logger.warning("API rate limit exceeded from %s", client_ip)
                return JsonResponse({
                    'error': 'API rate limit exceeded.',
                    'retry_after': 60,
                }, status=429)

        # Global rate limit
        if not self._check_rate_limit(client_ip, 'global'):
            logger.warning("Global rate limit exceeded from %s", client_ip)
            return JsonResponse({
                'error': 'Too many requests. Please slow down.',
                'retry_after': 60,
            }, status=429)

        return self.get_response(request)

    def _get_client_ip(self, request):
        """Get the client IP address, considering proxies."""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR', '127.0.0.1')
        return ip

    def _check_rate_limit(self, client_ip, limit_type):
        """Check if request is within rate limit. Returns True if allowed."""
        config = self.RATE_LIMITS[limit_type]
        key = f"ratelimit:{limit_type}:{client_ip}"
        now = time.time()
        window = config['window']
        max_requests = config['requests']

        # Try to use cache (Redis) first, fall back to in-memory
        try:
            # Use Redis-based rate limiting if available
            if hasattr(cache, 'incr'):
                count = cache.get(key, 0)
                if count >= max_requests:
                    return False
                cache.incr(key, 1)
                if count == 0:
                    cache.expire(key, window)
                return True
        except Exception:
            pass

        # Fallback to in-memory rate limiting
        with self._lock:
            # Clean old entries
            cutoff = now - window
            self._rate_limits[key] = [t for t in self._rate_limits[key] if t > cutoff]

            if len(self._rate_limits[key]) >= max_requests:
                return False

            self._rate_limits[key].append(now)
            return True


# =============================================================================
# GitHub Issue Creation for 5xx Errors
# =============================================================================

class ErrorReportingMiddleware:
    """
    Middleware that automatically creates GitHub issues for 5xx errors.

    Configure with environment variables:
    - GITHUB_TOKEN: Personal access token with repo scope
    - GITHUB_REPO: Repository in format 'owner/repo'
    - GITHUB_ISSUE_ENABLED: Set to 'true' to enable
    """

    # Track recently reported errors to avoid duplicates
    _reported_errors = {}
    _lock = Lock()
    DEDUP_WINDOW = 3600  # Don't report same error within 1 hour

    def __init__(self, get_response):
        self.get_response = get_response
        self.github_token = getattr(settings, 'GITHUB_TOKEN', '')
        self.github_repo = getattr(settings, 'GITHUB_REPO', '')
        self.enabled = getattr(settings, 'GITHUB_ISSUE_ENABLED', False)

    def __call__(self, request):
        response = self.get_response(request)
        return response

    def process_exception(self, request, exception):
        """Handle uncaught exceptions by creating GitHub issues."""
        if not self.enabled or not self.github_token or not self.github_repo:
            return None

        # Generate error fingerprint for deduplication
        tb = traceback.format_exc()
        error_hash = self._get_error_hash(exception, tb)

        # Check if we've already reported this error recently
        if self._is_recently_reported(error_hash):
            logger.debug("Skipping duplicate error report for %s", error_hash[:8])
            return None

        # Create GitHub issue asynchronously (don't block the request)
        try:
            self._create_github_issue(request, exception, tb, error_hash)
        except Exception as e:
            logger.error("Failed to create GitHub issue: %s", e)

        return None  # Let Django handle the exception normally

    def _get_error_hash(self, exception, traceback_str):
        """Generate a hash for error deduplication."""
        content = f"{type(exception).__name__}:{str(exception)}:{traceback_str}"
        return hashlib.sha256(content.encode()).hexdigest()

    def _is_recently_reported(self, error_hash):
        """Check if this error was recently reported."""
        now = time.time()
        with self._lock:
            # Clean old entries
            cutoff = now - self.DEDUP_WINDOW
            self._reported_errors = {
                h: t for h, t in self._reported_errors.items() if t > cutoff
            }

            if error_hash in self._reported_errors:
                return True

            self._reported_errors[error_hash] = now
            return False

    def _create_github_issue(self, request, exception, traceback_str, error_hash):
        """Create a GitHub issue for the error."""
        title = f"[Auto] 5xx Error: {type(exception).__name__}: {str(exception)[:100]}"

        # Sanitize request info (remove sensitive data)
        safe_headers = {
            k: v for k, v in request.META.items()
            if k.startswith('HTTP_') and 'AUTH' not in k.upper() and 'COOKIE' not in k.upper()
        }

        body = f"""## Automatic Error Report

**Error Type:** `{type(exception).__name__}`
**Error Message:** `{str(exception)}`
**Error Hash:** `{error_hash[:16]}`
**Timestamp:** {datetime.utcnow().isoformat()}Z

### Request Info
- **Path:** `{request.path}`
- **Method:** `{request.method}`
- **User Agent:** `{request.META.get('HTTP_USER_AGENT', 'Unknown')[:200]}`

### Traceback
```python
{traceback_str[:3000]}
```

---
*This issue was automatically created by the error reporting middleware.*
"""

        try:
            response = requests.post(
                f"https://api.github.com/repos/{self.github_repo}/issues",
                headers={
                    'Authorization': f'token {self.github_token}',
                    'Accept': 'application/vnd.github.v3+json',
                },
                json={
                    'title': title,
                    'body': body,
                    'labels': ['bug', 'auto-reported', '5xx-error'],
                },
                timeout=10,
            )

            if response.status_code == 201:
                issue_url = response.json().get('html_url', '')
                logger.info("Created GitHub issue: %s", issue_url)
            else:
                logger.warning("Failed to create GitHub issue: %s", response.text[:500])

        except Exception as e:
            logger.error("GitHub API error: %s", e)


# =============================================================================
# Security Headers Middleware
# =============================================================================

class SecurityHeadersMiddleware:
    """
    Add security headers to all responses.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Content Security Policy
        # Allow Tailwind CDN, Google Fonts, and inline styles/scripts for template functionality
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://fonts.gstatic.com; "
            "connect-src 'self' https://random-word-api.vercel.app; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self';"
        )
        response['Content-Security-Policy'] = csp

        # Prevent MIME type sniffing
        response['X-Content-Type-Options'] = 'nosniff'

        # Referrer policy
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        # Permissions policy
        response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'

        return response


# =============================================================================
# Input Sanitization Utilities
# =============================================================================

class InputSanitizer:
    """
    Utility class for sanitizing user input to prevent injection attacks.
    """

    # Characters that are safe in search keywords
    SAFE_KEYWORD_CHARS = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _-')

    # Maximum lengths for various inputs
    MAX_KEYWORD_LENGTH = 64
    MAX_EMAIL_LENGTH = 256
    MAX_TEXT_LENGTH = 1000
    MAX_NOTES_LENGTH = 500

    @classmethod
    def sanitize_keyword(cls, value):
        """Sanitize a search keyword."""
        if not value:
            return ''

        # Limit length
        value = str(value)[:cls.MAX_KEYWORD_LENGTH]

        # Remove unsafe characters
        sanitized = ''.join(c for c in value if c in cls.SAFE_KEYWORD_CHARS)

        # Normalize whitespace
        sanitized = ' '.join(sanitized.split())

        return sanitized.strip()

    @classmethod
    def sanitize_email(cls, value):
        """Sanitize an email address."""
        import re

        if not value:
            return None

        value = str(value).strip()[:cls.MAX_EMAIL_LENGTH]

        # Basic email pattern validation
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, value):
            return None

        return value.lower()

    @classmethod
    def sanitize_integer(cls, value, min_val=None, max_val=None, default=0):
        """Sanitize and validate an integer value."""
        try:
            # Handle common number formats
            if isinstance(value, str):
                value = value.replace(',', '').replace('_', '').strip()

            result = int(value)

            if min_val is not None and result < min_val:
                result = min_val
            if max_val is not None and result > max_val:
                result = max_val

            return result
        except (TypeError, ValueError):
            return default

    @classmethod
    def sanitize_text(cls, value, max_length=None):
        """Sanitize general text input."""
        if not value:
            return ''

        max_len = max_length or cls.MAX_TEXT_LENGTH
        value = str(value)[:max_len]

        # Remove null bytes and control characters (except newlines/tabs)
        import re
        value = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', value)

        return value.strip()

    @classmethod
    def sanitize_username(cls, value):
        """Sanitize a Reddit username."""
        import re

        if not value:
            return ''

        value = str(value).strip()

        # Remove /u/ or u/ prefix
        value = re.sub(r'^/?u/', '', value, flags=re.IGNORECASE)

        # Only allow valid Reddit username characters
        value = re.sub(r'[^a-zA-Z0-9_-]', '', value)

        return value[:20]  # Reddit usernames max 20 chars

    @classmethod
    def sanitize_job_id(cls, value):
        """Sanitize a job ID (should be hex string)."""
        import re

        if not value:
            return ''

        value = str(value).strip()[:64]

        # Job IDs should only contain hex characters
        if not re.match(r'^[a-fA-F0-9]+$', value):
            return ''

        return value.lower()
