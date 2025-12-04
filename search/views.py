"""
Django views for Reddit Sub Search.

Includes security hardening, input sanitization, and caching.
"""

import csv
import hashlib
import io
import logging
import re
from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.db.models import Count, Q
from django.http import JsonResponse, HttpResponse, StreamingHttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_GET, require_POST

from reddit_analyzer.middleware import InputSanitizer
from .models import QueryRun, Subreddit, RollingStats
from .tasks import submit_user_search, PRIORITY_USER

logger = logging.getLogger(__name__)


def home(request):
    """Homepage with sub search form and activity overview."""
    job_id = request.GET.get('job')

    if request.method == 'POST':
        return _handle_search_submission(request)

    # Get rolling 24h stats and summary stats for Database Stats panel
    rolling_stats = RollingStats.get_stats()
    stats = _get_summary_stats()

    # Recent user searches - only completed ones (not running/queued)
    recent_user_runs = list(
        QueryRun.objects.filter(
            source=QueryRun.Source.SUB_SEARCH,
            state__in=[QueryRun.State.COMPLETE, QueryRun.State.STOPPED, QueryRun.State.ERROR]
        )
        .order_by('-completed_at')[:8]
    )

    # Latest random search
    random_run = QueryRun.objects.filter(
        source=QueryRun.Source.AUTO_RANDOM
    ).order_by('-started_at').first()

    # Node stats
    from nodes.models import VolunteerNode
    node_stats = VolunteerNode.get_stats()
    volunteer_nodes = list(VolunteerNode.get_active_nodes(limit=6))

    # Queue count and queued runs
    queued_runs = list(
        QueryRun.objects.filter(
            state__in=[QueryRun.State.PENDING, QueryRun.State.QUEUED]
        ).order_by('started_at')[:5]
    )
    queue_count = len(queued_runs)

    return render(request, 'home.html', {
        'stats': stats,
        'rolling_stats': rolling_stats,
        'recent_user_runs': recent_user_runs,
        'random_run': random_run,
        'node_stats': node_stats,
        'volunteer_nodes': volunteer_nodes,
        'queue_count': queue_count,
        'queued_runs': queued_runs,
        'job_id': job_id,
        'nav_active': 'home',
    })


def _handle_search_submission(request):
    """Handle POST submission of search form with input sanitization."""
    # Get and sanitize form data
    keyword_raw = request.POST.get('keyword', '').strip()
    limit_raw = request.POST.get('limit', '1000').strip()
    unmoderated_only = request.POST.get('unmoderated_only') == 'on'
    exclude_nsfw = request.POST.get('exclude_nsfw') == 'on'
    min_subs_raw = request.POST.get('min_subs', '0').strip()
    activity_enabled = request.POST.get('activity_enabled') == 'on'
    activity_mode = request.POST.get('activity_mode', 'any').strip()
    activity_date_raw = request.POST.get('activity_date', '').strip()
    notification_email_raw = request.POST.get('notification_email', '').strip()

    # Sanitize keyword using the InputSanitizer - keyword is required
    keyword = InputSanitizer.sanitize_keyword(keyword_raw)
    if not keyword:
        messages.error(request, "Please enter a keyword to search for subreddits.")
        return redirect('home')

    # Sanitize and validate email
    notification_email = None
    if notification_email_raw:
        notification_email = InputSanitizer.sanitize_email(notification_email_raw)
        if notification_email_raw and not notification_email:
            messages.warning(request, "Invalid email format. Notification will not be sent.")

    # Validate activity mode
    if activity_mode not in ('any', 'active_after', 'inactive_before'):
        activity_mode = 'any'

    # Parse limit with sanitization
    limit = InputSanitizer.sanitize_integer(limit_raw, min_val=1, max_val=100000, default=1000)
    if limit > settings.PUBLIC_API_LIMIT_CAP:
        messages.info(
            request,
            f"API checks limited to {settings.PUBLIC_API_LIMIT_CAP} subreddits per run."
        )
        limit = settings.PUBLIC_API_LIMIT_CAP

    # Parse min subscribers with sanitization
    min_subs = InputSanitizer.sanitize_integer(min_subs_raw, min_val=0, max_val=10_000_000, default=0)

    # Parse activity threshold with strict date validation
    activity_threshold_utc = None
    if activity_enabled and activity_mode in ('active_after', 'inactive_before') and activity_date_raw:
        # Strict date format validation
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', activity_date_raw):
            messages.error(request, "Invalid date format. Use YYYY-MM-DD.")
            return redirect('home')
        try:
            dt = datetime.strptime(activity_date_raw, '%Y-%m-%d')
            # Validate reasonable date range (not too far in past or future)
            now = datetime.now()
            min_date = datetime(2005, 1, 1)  # Reddit's founding year
            if dt < min_date or dt > now:
                raise ValueError("Date out of valid range")
            activity_threshold_utc = int(dt.timestamp())
        except Exception:
            messages.error(request, "Invalid date provided.")
            return redirect('home')
    elif not activity_enabled:
        activity_mode = 'any'

    # Submit the search job
    try:
        job_id = submit_user_search(
            keyword=keyword,
            limit=limit,
            unmoderated_only=unmoderated_only,
            exclude_nsfw=exclude_nsfw,
            min_subs=min_subs,
            activity_mode=activity_mode,
            activity_threshold_utc=activity_threshold_utc,
            notification_email=notification_email,
        )
    except Exception as e:
        logger.exception("Failed to submit search job: %s", e)
        messages.error(request, "Failed to submit search. Please try again.")
        return redirect('home')

    return redirect('home_with_job', job_id=job_id)


def home_with_job(request, job_id):
    """Homepage with active job tracking."""
    # Sanitize job_id before using in URL
    sanitized_job_id = InputSanitizer.sanitize_job_id(job_id)
    if not sanitized_job_id:
        return redirect('home')
    return redirect(f'/?job={sanitized_job_id}')


def _get_summary_stats():
    """Get summary statistics for display with caching."""
    cache_key = 'summary_stats'
    cached = cache.get(cache_key)
    if cached:
        return cached

    total_subs = Subreddit.objects.count()
    last_indexed = Subreddit.objects.order_by('-updated_at').values_list('updated_at', flat=True).first()
    total_runs = QueryRun.objects.count()
    last_run = QueryRun.objects.order_by('-started_at').values_list('started_at', flat=True).first()

    stats = {
        'total_subreddits': total_subs,
        'last_indexed': last_indexed,
        'total_runs': total_runs,
        'last_run_started': last_run,
    }

    cache.set(cache_key, stats, getattr(settings, 'CACHE_TIMEOUT_STATS', 60))
    return stats


def help_page(request):
    """Help page."""
    return render(request, 'help.html')


def developer_docs(request):
    """Developer documentation page."""
    return render(request, 'developer_docs.html')


def logs(request):
    """View search history logs."""
    entries = list(QueryRun.objects.order_by('-started_at')[:30])

    job_stats = {
        'total': QueryRun.objects.filter(source=QueryRun.Source.SUB_SEARCH).count(),
        'completed': QueryRun.objects.filter(
            source=QueryRun.Source.SUB_SEARCH,
            state=QueryRun.State.COMPLETE
        ).count(),
        'failed': QueryRun.objects.filter(
            source=QueryRun.Source.SUB_SEARCH,
            state=QueryRun.State.ERROR
        ).count(),
        'pending': QueryRun.objects.filter(
            source=QueryRun.Source.SUB_SEARCH,
            state__in=[QueryRun.State.PENDING, QueryRun.State.QUEUED, QueryRun.State.RUNNING]
        ).count(),
    }

    queue_count = QueryRun.objects.filter(
        state__in=[QueryRun.State.PENDING, QueryRun.State.QUEUED]
    ).count()

    return render(request, 'logs.html', {
        'entries': entries,
        'job_stats': job_stats,
        'queue_count': queue_count,
        'nav_active': None,
    })


def all_subs(request):
    """Browse all subreddits with filtering."""
    job_id = request.GET.get('job_id', '')

    initial_filters = {
        'q': request.GET.get('q', '').strip(),
        'min_subs': request.GET.get('min_subs', '').strip(),
        'unmoderated': request.GET.get('unmoderated', '').strip(),
        'nsfw': request.GET.get('nsfw', '').strip(),
        'sort': request.GET.get('sort', 'subscribers').strip() or 'subscribers',
        'order': request.GET.get('order', 'desc').strip() or 'desc',
        'job_id': job_id,
    }

    # If job_id provided, pre-populate filters from job config
    if job_id:
        try:
            job = QueryRun.objects.get(job_id=job_id)
            if not initial_filters['q'] and job.keyword:
                initial_filters['q'] = job.keyword
            if not initial_filters['min_subs'] and job.min_subscribers:
                initial_filters['min_subs'] = str(job.min_subscribers)
            if not initial_filters['unmoderated'] and job.unmoderated_only:
                initial_filters['unmoderated'] = 'true'
            if not initial_filters['nsfw'] and job.exclude_nsfw:
                initial_filters['nsfw'] = 'false'
        except QueryRun.DoesNotExist:
            pass

    stats = _get_summary_stats()

    return render(request, 'all_subs.html', {
        'initial_filters': initial_filters,
        'nav_active': 'allsubs',
        'stats': stats,
    })


@require_GET
def status(request, job_id):
    """Get job status as JSON with input validation."""
    # Sanitize job_id
    sanitized_job_id = InputSanitizer.sanitize_job_id(job_id)
    if not sanitized_job_id:
        return JsonResponse({'error': 'invalid job id'}, status=400)

    # Check cache first for completed jobs
    cache_key = f"job_status:{sanitized_job_id}"
    cached = cache.get(cache_key)
    if cached and cached.get('done'):
        return JsonResponse(cached)

    try:
        job = QueryRun.objects.get(job_id=sanitized_job_id)
    except QueryRun.DoesNotExist:
        return JsonResponse({'error': 'unknown job'}, status=404)

    data = job.to_status_dict()

    # Add queue info
    queue_count = QueryRun.objects.filter(
        state__in=[QueryRun.State.PENDING, QueryRun.State.QUEUED]
    ).count()
    data['queue_backlog'] = queue_count
    data['max_concurrent'] = settings.MAX_CONCURRENT_JOBS
    data['rate_limit_delay'] = settings.RATE_LIMIT_DELAY

    # Cache completed jobs longer
    if data.get('done'):
        cache.set(cache_key, data, 3600)  # 1 hour for completed jobs
    else:
        cache.set(cache_key, data, getattr(settings, 'CACHE_TIMEOUT_JOBS', 30))

    return JsonResponse(data)


@require_POST
def stop_job(request, job_id):
    """Stop a running job with input validation."""
    # Sanitize job_id
    sanitized_job_id = InputSanitizer.sanitize_job_id(job_id)
    if not sanitized_job_id:
        return JsonResponse({'ok': False, 'error': 'invalid job id'}, status=400)

    try:
        job = QueryRun.objects.get(job_id=sanitized_job_id)
    except QueryRun.DoesNotExist:
        return JsonResponse({'ok': False, 'error': 'unknown job'}, status=404)

    if job.is_complete:
        return JsonResponse({'ok': False, 'error': 'already done'}, status=400)

    # Mark as stopped
    job.mark_stopped()

    # Invalidate job status cache
    cache.delete(f"job_status:{sanitized_job_id}")

    # Try to revoke the Celery task
    if job.celery_task_id:
        try:
            from reddit_analyzer.celery import app
            app.control.revoke(job.celery_task_id, terminate=True)
        except Exception:
            logger.warning("Failed to revoke Celery task %s", job.celery_task_id)

    return JsonResponse({'ok': True, 'message': 'Stopping current run'})


@require_GET
def job_download_csv(request, job_id):
    """Download job results as CSV - all DB matches for the keyword."""
    # Sanitize job_id
    sanitized_job_id = InputSanitizer.sanitize_job_id(job_id)
    if not sanitized_job_id:
        return HttpResponse("Invalid job ID", status=400)

    try:
        job = QueryRun.objects.get(job_id=sanitized_job_id)
    except QueryRun.DoesNotExist:
        return HttpResponse("Job not found", status=404)

    # Get ALL subreddits matching the keyword in name, title, or description
    # This matches the count shown in Recent Search Results
    keyword = job.keyword
    if keyword:
        subreddits = Subreddit.objects.filter(
            Q(name__icontains=keyword) |
            Q(title__icontains=keyword) |
            Q(public_description__icontains=keyword)
        ).order_by('-subscribers')
    else:
        # No keyword means no results
        subreddits = Subreddit.objects.none()

    if not subreddits.exists():
        return HttpResponse("No matching subreddits found for this keyword.", status=404)

    fieldnames = [
        'display_name_prefixed', 'title', 'public_description', 'subscribers',
        'mod_count', 'is_unmoderated', 'is_nsfw', 'last_activity_utc',
        'updated_at', 'url', 'source'
    ]

    def generate():
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)

        for sub in subreddits:
            row = {
                'display_name_prefixed': sub.display_name_prefixed,
                'title': sub.title,
                'public_description': sub.public_description,
                'subscribers': sub.subscribers,
                'mod_count': sub.mod_count,
                'is_unmoderated': sub.is_unmoderated,
                'is_nsfw': sub.is_nsfw,
                'last_activity_utc': sub.last_activity_utc,
                'updated_at': sub.updated_at.isoformat() if sub.updated_at else None,
                'url': sub.url,
                'source': sub.source,
            }
            writer.writerow(row)
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)

    response = StreamingHttpResponse(generate(), content_type='text/csv')
    # Use keyword in filename for clarity
    safe_keyword = re.sub(r'[^a-zA-Z0-9_-]', '_', keyword or 'all')[:30]
    response['Content-Disposition'] = f'attachment; filename=subsearch_{safe_keyword}.csv'
    return response


@require_GET
def api_recent_runs(request):
    """Get recent runs as JSON."""
    limit = min(max(int(request.GET.get('limit', 5) or 5), 1), 50)
    source_filter = request.GET.get('source', '')

    # Build query based on source filter
    if source_filter == 'random':
        queryset = QueryRun.objects.filter(source=QueryRun.Source.RANDOM)
    elif source_filter == 'manual':
        queryset = QueryRun.objects.filter(source=QueryRun.Source.SUB_SEARCH)
    else:
        queryset = QueryRun.objects.filter(source=QueryRun.Source.SUB_SEARCH)

    runs = queryset.filter(completed_at__isnull=False).order_by('-completed_at')[:limit]

    return JsonResponse({
        'runs': [
            {
                'job_id': r.job_id,
                'keyword': r.keyword,
                'started_at': r.started_at.isoformat() if r.started_at else None,
                'completed_at': r.completed_at.isoformat() if r.completed_at else None,
                'result_count': r.result_count,
                'error': r.error,
                'source': r.source,
            }
            for r in runs
        ]
    })


@require_GET
def api_queue(request):
    """Get queue status with priority separation and running job info."""
    limit = min(max(int(request.GET.get('limit', 10) or 10), 1), 50)

    # Get currently running job
    running_job = QueryRun.objects.filter(state=QueryRun.State.RUNNING).first()

    # Get queued jobs - user jobs first (priority 0), then auto jobs (priority 9)
    queued_jobs = QueryRun.objects.filter(
        state__in=[QueryRun.State.PENDING, QueryRun.State.QUEUED]
    ).order_by('priority', 'started_at')[:limit]

    # Calculate average job time
    avg_time = _calculate_average_job_time()

    queue_items = []
    for idx, job in enumerate(queued_jobs):
        # Only include jobs with keywords (no "all subreddits" searches)
        if not job.keyword:
            continue

        eta_start = int(idx * avg_time)
        eta_completion = int((idx + 1) * avg_time)

        queue_items.append({
            'job_id': job.job_id,
            'keyword': job.keyword,
            'limit': job.limit_value,
            'source': job.source,
            'priority': job.priority,
            'position': idx + 1,
            'eta_start_seconds': eta_start,
            'eta_completion_seconds': eta_completion,
            'is_manual': job.source == QueryRun.Source.SUB_SEARCH,
        })

    # Build running job info
    running_info = None
    if running_job:
        running_info = {
            'job_id': running_job.job_id,
            'keyword': running_job.keyword,
            'source': running_job.source,
            'checked': running_job.checked_count or 0,
            'found': running_job.found_count or 0,
            'limit': running_job.limit_value,
            'is_manual': running_job.source == QueryRun.Source.SUB_SEARCH,
        }

    return JsonResponse({
        'running': running_info,
        'queue': queue_items,
        'total_queued': len(queue_items),
        'avg_job_time_seconds': avg_time,
    })


@require_GET
def api_subreddits(request):
    """Search subreddits API endpoint with caching and input sanitization."""
    # Sanitize and validate inputs
    q = InputSanitizer.sanitize_keyword(request.GET.get('q', ''))
    unmoderated = _parse_bool(request.GET.get('unmoderated'))
    nsfw = _parse_bool(request.GET.get('nsfw'))
    min_subs = InputSanitizer.sanitize_integer(
        request.GET.get('min_subs'), min_val=0, max_val=100_000_000, default=None
    )
    max_subs = InputSanitizer.sanitize_integer(
        request.GET.get('max_subs'), min_val=0, max_val=100_000_000, default=None
    )
    page = max(InputSanitizer.sanitize_integer(request.GET.get('page'), default=1), 1)
    page_size = min(max(InputSanitizer.sanitize_integer(
        request.GET.get('page_size'), default=50
    ), 1), 200)
    sort = request.GET.get('sort', 'subscribers') or 'subscribers'
    order = request.GET.get('order', 'desc') or 'desc'
    job_id_raw = request.GET.get('job_id', '').strip()
    job_id = InputSanitizer.sanitize_job_id(job_id_raw) if job_id_raw else ''

    # Validate sort field (prevent SQL injection via sort)
    # Map frontend field names to database field names
    sort_field_map = {
        'mod_activity': 'last_activity_utc',
    }
    sort = sort_field_map.get(sort, sort)
    valid_sort_fields = {'name', 'title', 'subscribers', 'updated_at', 'first_seen_at', 'mod_count', 'last_activity_utc'}
    if sort not in valid_sort_fields:
        sort = 'subscribers'

    # Validate order
    if order.lower() not in ('asc', 'desc'):
        order = 'desc'

    # Generate cache key based on query parameters
    cache_params = f"{q}:{unmoderated}:{nsfw}:{min_subs}:{max_subs}:{page}:{page_size}:{sort}:{order}:{job_id}"
    cache_key = f"api_subreddits:{hashlib.md5(cache_params.encode()).hexdigest()}"

    # Try to get from cache
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse(cached)

    # Build queryset
    qs = Subreddit.objects.all()

    if q:
        # Use icontains which is safe from SQL injection
        qs = qs.filter(name__icontains=q)

    if unmoderated is not None:
        qs = qs.filter(is_unmoderated=unmoderated)

    if nsfw is not None:
        qs = qs.filter(is_nsfw=nsfw)

    if min_subs is not None:
        qs = qs.filter(subscribers__gte=min_subs)

    if max_subs is not None:
        qs = qs.filter(subscribers__lte=max_subs)

    if job_id:
        try:
            job = QueryRun.objects.get(job_id=job_id)
            qs = qs.filter(last_seen_run=job)
        except QueryRun.DoesNotExist:
            result = {'total': 0, 'page': page, 'page_size': page_size, 'rows': []}
            cache.set(cache_key, result, getattr(settings, 'CACHE_TIMEOUT_SUBREDDITS', 300))
            return JsonResponse(result)

    # Sorting - use validated sort field
    sort_field = sort if sort in valid_sort_fields else 'subscribers'
    if order.lower() == 'asc':
        qs = qs.order_by(sort_field)
    else:
        qs = qs.order_by(f'-{sort_field}')

    # Pagination with query optimization
    # Use select_related/prefetch_related if needed
    total = qs.count()
    offset = (page - 1) * page_size

    # Limit maximum offset to prevent performance issues
    max_offset = 10000
    if offset > max_offset:
        result = {
            'total': total,
            'page': page,
            'page_size': page_size,
            'rows': [],
            'error': f'Page too deep. Maximum offset is {max_offset}.',
        }
        return JsonResponse(result)

    rows = list(qs.only(
        'name', 'display_name_prefixed', 'title', 'public_description',
        'url', 'subscribers', 'is_unmoderated', 'is_nsfw',
        'last_activity_utc', 'mod_count', 'source', 'first_seen_at', 'updated_at'
    )[offset:offset + page_size])

    result = {
        'total': total,
        'page': page,
        'page_size': page_size,
        'rows': [sub.to_dict() for sub in rows],
    }

    # Cache the result
    cache.set(cache_key, result, getattr(settings, 'CACHE_TIMEOUT_SUBREDDITS', 300))

    return JsonResponse(result)


def _calculate_average_job_time():
    """Calculate average job completion time with caching."""
    cache_key = 'avg_job_time'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    from django.db.models import Avg

    avg = QueryRun.objects.filter(
        source=QueryRun.Source.SUB_SEARCH,
        state=QueryRun.State.COMPLETE,
        duration_ms__isnull=False,
        duration_ms__lt=600000,  # Less than 10 minutes
    ).aggregate(avg=Avg('duration_ms'))['avg']

    result = int(avg / 1000) if avg else 60  # Convert to seconds, default 60

    cache.set(cache_key, result, 300)  # Cache for 5 minutes
    return result


def _parse_bool(value):
    """Parse boolean from query string."""
    if value is None or value == '':
        return None
    val = str(value).strip().lower()
    if val in ('1', 'true', 'yes', 'y', 'on'):
        return True
    if val in ('0', 'false', 'no', 'n', 'off'):
        return False
    return None


def favicon(request):
    """Serve inline SVG favicon."""
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
        "<defs><radialGradient id='g' cx='50%' cy='50%' r='60%'>"
        "<stop offset='0%' stop-color='#22d3ee'/><stop offset='100%' stop-color='#7c3aed'/></radialGradient></defs>"
        "<rect width='64' height='64' rx='14' fill='url(#g)'/>"
        "<circle cx='32' cy='32' r='10' fill='white' opacity='0.9'/></svg>"
    )
    return HttpResponse(svg, content_type='image/svg+xml')
