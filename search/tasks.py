"""
Celery tasks for Reddit Sub Search.

Priority levels:
- 0-3: User searches (highest priority, processed first)
- 4-6: Normal priority
- 7-9: Automated searches (lowest priority, processed last)
"""

import logging
import random
import re
import time
import uuid

import requests
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from datetime import timedelta

from .models import QueryRun, Subreddit

logger = logging.getLogger(__name__)

# Priority constants
PRIORITY_USER = 0  # Highest priority for user searches
PRIORITY_AUTO = 9  # Lowest priority for automated searches


def get_reddit_config():
    """Get Reddit API configuration from Django settings."""
    return {
        'client_id': settings.REDDIT_CLIENT_ID,
        'client_secret': settings.REDDIT_CLIENT_SECRET,
        'username': settings.REDDIT_USERNAME,
        'password': settings.REDDIT_PASSWORD,
        'user_agent': settings.REDDIT_USER_AGENT,
        'timeout': settings.REDDIT_TIMEOUT,
    }


def find_unmoderated_subreddits(
    limit=100,
    name_keyword=None,
    unmoderated_only=True,
    exclude_nsfw=False,
    min_subscribers=0,
    activity_mode="any",
    activity_threshold_utc=None,
    progress_callback=None,
    stop_callback=None,
    rate_limit_delay=0.0,  # Deprecated - PRAW handles rate limiting
    include_all=False,
    exclude_names=None,
    result_callback=None,
):
    """
    Connect to Reddit API and find subreddits matching the given criteria.

    Optimized for speed:
    - PRAW handles rate limiting automatically (100 req/min for OAuth)
    - Moderator lookups only happen when unmoderated_only=True
    - Activity lookups only happen when activity filtering is enabled
    - No manual delays between requests
    """
    import praw
    import prawcore

    cfg = get_reddit_config()

    # Build Reddit instance with higher ratelimit tolerance
    requestor_kwargs = {"timeout": max(10, min(int(cfg.get('timeout') or 30), 120))}
    reddit_kwargs = {
        'client_id': cfg['client_id'],
        'client_secret': cfg['client_secret'],
        'user_agent': cfg['user_agent'],
        'requestor_kwargs': requestor_kwargs,
        'check_for_async': False,
        'ratelimit_seconds': 300,  # Allow PRAW to wait up to 5min for rate limits
    }

    if cfg.get('username') and cfg.get('password') and \
       cfg['username'] != 'your_username_here' and cfg['password'] != 'your_password_here':
        reddit_kwargs.update({'username': cfg['username'], 'password': cfg['password']})
        auth_mode = 'script'
    else:
        auth_mode = 'read-only'

    reddit = praw.Reddit(**reddit_kwargs)
    if auth_mode == 'read-only':
        try:
            reddit.read_only = True
        except Exception:
            pass

    normalized_excludes = {name.strip().lower() for name in (exclude_names or set()) if name and name.strip()}

    filtered_subs = []
    evaluated_subs = []
    checked = 0

    # Determine what extra API calls we need
    need_moderator_check = unmoderated_only
    need_activity_check = activity_mode in ("active_after", "inactive_before") and activity_threshold_utc

    logger.info("Searching subreddits: keyword=%r limit=%d unmod_check=%s activity_check=%s",
                name_keyword, limit, need_moderator_check, need_activity_check)

    # Get subreddit iterator - use higher breadth for more discovery
    subreddit_iter = None
    if name_keyword:
        try:
            from subsearch.broadened_search import broadened_subreddit_search
            subreddit_iter = broadened_subreddit_search(
                reddit=reddit,
                query=name_keyword,
                limit=limit,
                delay=0.0,  # PRAW handles rate limiting
                include_over_18=not exclude_nsfw,
                breadth=5,  # Maximum breadth for thorough discovery
                popular_sip=min(500, limit),
            )
        except Exception as e:
            logger.warning("Broadened search error: %s. Falling back to new subreddits.", e)
            subreddit_iter = reddit.subreddits.new(limit=limit)
    else:
        subreddit_iter = reddit.subreddits.new(limit=limit)

    # Progress update frequency - don't update too often
    last_progress_update = 0
    PROGRESS_UPDATE_INTERVAL = 10

    for subreddit in subreddit_iter:
        # Check for stop signal
        if stop_callback and stop_callback():
            logger.info("Stop requested; ending early. Checked=%d, found=%d", checked, len(filtered_subs))
            break

        checked += 1

        # Throttle progress updates to reduce DB writes
        if progress_callback and (checked - last_progress_update) >= PROGRESS_UPDATE_INTERVAL:
            try:
                progress_callback(checked=checked, found=len(filtered_subs))
                last_progress_update = checked
            except Exception:
                pass

        latest_post_utc = None
        passes_filters = True

        try:
            # Get basic info - these are already loaded from the search response
            display_name = getattr(subreddit, 'display_name', 'unknown')
            display_name_prefixed = getattr(subreddit, 'display_name_prefixed', f"r/{display_name}")
            title = getattr(subreddit, 'title', display_name)
            public_description = getattr(subreddit, 'public_description', '') or ''
            is_nsfw = bool(getattr(subreddit, 'over18', False))

            # Skip if already in our exclude set
            name_key = (display_name or "").strip().lower()
            if normalized_excludes and name_key in normalized_excludes:
                continue

            # Get subscriber count (already in response, no extra API call)
            subscribers = None
            try:
                subscribers = subreddit.subscribers
            except (praw.exceptions.PRAWException, prawcore.exceptions.PrawcoreException, AttributeError):
                subscribers = None
            subs_count = subscribers if isinstance(subscribers, int) else (subscribers or 0)

            # OPTIMIZATION: Only fetch moderators if unmoderated_only filter is enabled
            mod_count = None
            if need_moderator_check:
                try:
                    moderators = list(subreddit.moderator())
                    real_mods = [
                        mod for mod in moderators
                        if getattr(mod, 'name', '').lower() not in ('automoderator', '')
                    ]
                    mod_count = len(real_mods)
                except (praw.exceptions.PRAWException, prawcore.exceptions.PrawcoreException, AttributeError):
                    mod_count = None

            # OPTIMIZATION: Only fetch activity if activity filter is enabled
            if need_activity_check:
                try:
                    for post in subreddit.new(limit=1):
                        latest_post_utc = getattr(post, 'created_utc', None)
                        break
                except (praw.exceptions.PRAWException, prawcore.exceptions.PrawcoreException, AttributeError):
                    pass

            # Build sub_info
            sub_info = {
                'name': display_name,
                'display_name_prefixed': display_name_prefixed,
                'title': title,
                'public_description': public_description,
                'subscribers': subs_count,
                'url': f"https://reddit.com{getattr(subreddit, 'url', '/')}",
                'is_unmoderated': bool(mod_count == 0) if mod_count is not None else None,
                'is_nsfw': is_nsfw,
                'mod_count': mod_count,
                'last_activity_utc': latest_post_utc,
            }

            # Save to database via callback
            if result_callback:
                try:
                    result_callback(dict(sub_info))
                except Exception:
                    logger.debug("Result callback failed for %s", sub_info.get("name"), exc_info=True)

            evaluated_subs.append(sub_info)

            # Apply filters
            if exclude_nsfw and is_nsfw:
                passes_filters = False

            if passes_filters and subs_count < (min_subscribers or 0):
                passes_filters = False

            if passes_filters and need_activity_check:
                if latest_post_utc is None:
                    passes_filters = False
                elif activity_mode == "active_after" and latest_post_utc < activity_threshold_utc:
                    passes_filters = False
                elif activity_mode == "inactive_before" and latest_post_utc >= activity_threshold_utc:
                    passes_filters = False

            if passes_filters and unmoderated_only:
                if mod_count is None or mod_count > 0:
                    passes_filters = False

            if passes_filters:
                filtered_subs.append(sub_info)
                if unmoderated_only and sub_info.get('is_unmoderated'):
                    logger.info("Found unmoderated: %s (%s subscribers)",
                               sub_info['display_name_prefixed'], sub_info['subscribers'])

        except Exception:
            pass

        if checked % 100 == 0:
            logger.debug("Progress: checked=%d found=%d", checked, len(filtered_subs))

    # Final progress update
    if progress_callback:
        try:
            progress_callback(checked=checked, found=len(filtered_subs))
        except Exception:
            pass

    logger.info("Total checked: %d, found: %d", checked, len(filtered_subs))

    if include_all:
        return {
            "results": filtered_subs,
            "evaluated": evaluated_subs,
            "checked": checked,
        }
    return filtered_subs


@shared_task(bind=True, max_retries=0, soft_time_limit=3300, time_limit=3600)
def run_sub_search(self, job_id: str):
    """
    Execute a sub search job.

    This task processes user-submitted search requests with highest priority.
    Jobs are tracked in the database and can be stopped via the stop endpoint.
    """
    try:
        query_run = QueryRun.objects.get(job_id=job_id)
    except QueryRun.DoesNotExist:
        logger.error("Job %s not found in database", job_id)
        return {'error': 'Job not found'}

    # Update task ID and mark as running
    query_run.celery_task_id = self.request.id
    query_run.mark_running()

    # Track if we should stop
    should_stop = False

    def check_stop():
        nonlocal should_stop
        if should_stop:
            return True
        # Refresh from database to check if stopped
        query_run.refresh_from_db()
        if query_run.state == QueryRun.State.STOPPED:
            should_stop = True
            return True
        return False

    def update_progress(checked, found):
        query_run.update_progress(checked=checked, found=found, phase='api_search')

    # Collect results to persist
    results_buffer = []
    batch_size = settings.PERSIST_BATCH_SIZE

    def persist_result(sub_info):
        results_buffer.append(sub_info)
        if len(results_buffer) >= batch_size:
            _flush_results(query_run, results_buffer.copy())
            results_buffer.clear()

    try:
        # Query existing matches from database first
        existing_matches = _query_existing_matches(query_run)
        existing_names = {(row.name or '').strip().lower() for row in existing_matches}

        query_run.update_progress(found=len(existing_matches), phase='api_search')

        # Run the search
        payload = find_unmoderated_subreddits(
            limit=min(query_run.limit_value or 1000, settings.PUBLIC_API_LIMIT_CAP),
            name_keyword=query_run.keyword,
            unmoderated_only=query_run.unmoderated_only,
            exclude_nsfw=query_run.exclude_nsfw,
            min_subscribers=query_run.min_subscribers,
            activity_mode=query_run.activity_mode or 'any',
            activity_threshold_utc=query_run.activity_threshold_utc,
            progress_callback=update_progress,
            stop_callback=check_stop,
            rate_limit_delay=settings.RATE_LIMIT_DELAY,
            include_all=True,
            exclude_names=existing_names,
            result_callback=persist_result,
        )

        # Flush remaining results
        if results_buffer:
            _flush_results(query_run, results_buffer)

        # Count total keyword matches in database AFTER search completes
        # This gives accurate count of all subs matching the keyword
        total_count = _count_keyword_matches(query_run.keyword)

        query_run.mark_complete(result_count=total_count)
        api_evaluated = payload.get('evaluated', []) if isinstance(payload, dict) else payload
        logger.info("Job %s completed with %d total matches in DB (%d evaluated from API)",
                   job_id, total_count, len(api_evaluated))

        # Send email notification if requested
        if query_run.notification_email:
            send_completion_notification.delay(job_id)

        return {
            'job_id': job_id,
            'result_count': total_count,
            'checked': payload.get('checked', 0) if isinstance(payload, dict) else len(api_results),
        }

    except SoftTimeLimitExceeded:
        # Even on timeout, count what's in the DB
        total_count = _count_keyword_matches(query_run.keyword)
        query_run.mark_complete(result_count=total_count, error='Task timed out')
        logger.warning("Job %s timed out (still found %d matches in DB)", job_id, total_count)
        # Send notification even on timeout
        if query_run.notification_email:
            send_completion_notification.delay(job_id)
        return {'error': 'Task timed out'}

    except Exception as e:
        logger.exception("Job %s failed: %s", job_id, e)
        # Even on error, count what's in the DB
        total_count = _count_keyword_matches(query_run.keyword)
        query_run.mark_complete(result_count=total_count, error=str(e))
        # Send notification even on error
        if query_run.notification_email:
            send_completion_notification.delay(job_id)
        return {'error': str(e)}


def _query_existing_matches(query_run):
    """Query database for existing subreddit matches by keyword only.

    Note: This only matches by keyword (name/title/description).
    User filters (unmoderated, nsfw, subscribers) are NOT applied here
    because we want the result count to reflect keyword matches,
    not filtered results. Filters are applied when viewing/downloading.
    """
    from django.db.models import Q

    qs = Subreddit.objects.all()

    if query_run.keyword:
        # Search by name, title, and description for loose keyword matching
        keyword = query_run.keyword
        qs = qs.filter(
            Q(name__icontains=keyword) |
            Q(title__icontains=keyword) |
            Q(public_description__icontains=keyword)
        )
    else:
        # No keyword means no matches from existing DB
        return []

    # Limit to reasonable amount
    return list(qs.order_by('-subscribers')[:5000])


def _count_keyword_matches(keyword):
    """Count total subreddits in database matching a keyword.

    Returns the count of all subs where the keyword appears in
    name, title, or description. This is used for the final
    result count after a search completes.
    """
    from django.db.models import Q

    if not keyword:
        return 0

    return Subreddit.objects.filter(
        Q(name__icontains=keyword) |
        Q(title__icontains=keyword) |
        Q(public_description__icontains=keyword)
    ).count()


def _flush_results(query_run, results):
    """Persist subreddit results to database."""
    if not results:
        return

    with transaction.atomic():
        for sub_info in results:
            Subreddit.upsert_from_dict(
                sub_info,
                query_run=query_run,
                keyword=query_run.keyword,
                source=query_run.source
            )


@shared_task(bind=True, max_retries=0)
def run_random_search(self):
    """
    Execute a random keyword search.

    This task runs with LOW priority (9) so user searches are processed first.
    """
    # Fetch random keyword
    keyword = _fetch_random_keyword()
    if not keyword:
        logger.warning("Failed to get random keyword")
        return {'error': 'No keyword'}

    # Create job record
    job_id = uuid.uuid4().hex
    limit = min(settings.RANDOM_SEARCH_LIMIT, settings.PUBLIC_API_LIMIT_CAP)

    query_run = QueryRun.objects.create(
        job_id=job_id,
        source=QueryRun.Source.AUTO_RANDOM,
        state=QueryRun.State.QUEUED,
        keyword=keyword,
        limit_value=limit,
        unmoderated_only=False,
        exclude_nsfw=False,
        min_subscribers=0,
        celery_task_id=self.request.id,
        priority=PRIORITY_AUTO,
    )

    # Mark as running now that we're actually executing
    query_run.mark_running()
    logger.info("Starting random search: keyword=%s job_id=%s", keyword, job_id)

    try:
        results_buffer = []

        def persist_result(sub_info):
            results_buffer.append(sub_info)
            if len(results_buffer) >= settings.PERSIST_BATCH_SIZE:
                _flush_results(query_run, results_buffer.copy())
                results_buffer.clear()

        payload = find_unmoderated_subreddits(
            limit=limit,
            name_keyword=keyword,
            unmoderated_only=False,
            exclude_nsfw=False,
            min_subscribers=0,
            activity_mode='any',
            rate_limit_delay=settings.AUTO_INGEST_DELAY,
            include_all=True,
            result_callback=persist_result,
        )

        if results_buffer:
            _flush_results(query_run, results_buffer)

        api_results = payload.get('results', []) if isinstance(payload, dict) else payload
        query_run.mark_complete(result_count=len(api_results))

        logger.info("Random search %s completed: %d results", job_id, len(api_results))
        return {'job_id': job_id, 'keyword': keyword, 'result_count': len(api_results)}

    except Exception as e:
        logger.exception("Random search %s failed: %s", job_id, e)
        query_run.mark_complete(result_count=0, error=str(e))
        return {'error': str(e)}


@shared_task(bind=True, max_retries=0)
def run_auto_ingest(self):
    """
    Execute auto-ingest job for configured keywords.

    This task runs with LOW priority (9) so user searches are processed first.
    Only runs if AUTO_INGEST_KEYWORDS is configured with actual keywords.
    """
    keywords = settings.AUTO_INGEST_KEYWORDS
    if not keywords:
        logger.info("Auto-ingest skipped: no keywords configured")
        return {'status': 'skipped', 'reason': 'no keywords configured'}

    for keyword in keywords:
        if not keyword:
            continue  # Skip empty keywords
        job_id = uuid.uuid4().hex
        label = keyword.replace(' ', '-').lower()

        query_run = QueryRun.objects.create(
            job_id=job_id,
            source=QueryRun.Source.AUTO_INGEST,
            state=QueryRun.State.QUEUED,
            keyword=keyword,
            limit_value=settings.AUTO_INGEST_LIMIT,
            unmoderated_only=False,
            exclude_nsfw=False,
            min_subscribers=settings.AUTO_INGEST_MIN_SUBS,
            celery_task_id=self.request.id,
            priority=PRIORITY_AUTO,
        )

        # Mark as running now that we're actually executing
        query_run.mark_running()
        logger.info("Starting auto-ingest: keyword=%s job_id=%s", label, job_id)

        try:
            results_buffer = []

            def persist_result(sub_info):
                results_buffer.append(sub_info)
                if len(results_buffer) >= settings.PERSIST_BATCH_SIZE:
                    _flush_results(query_run, results_buffer.copy())
                    results_buffer.clear()

            payload = find_unmoderated_subreddits(
                limit=settings.AUTO_INGEST_LIMIT,
                name_keyword=keyword,
                unmoderated_only=False,
                exclude_nsfw=False,
                min_subscribers=settings.AUTO_INGEST_MIN_SUBS,
                activity_mode='any',
                rate_limit_delay=settings.AUTO_INGEST_DELAY,
                include_all=True,
                result_callback=persist_result,
            )

            if results_buffer:
                _flush_results(query_run, results_buffer)

            api_results = payload.get('results', []) if isinstance(payload, dict) else payload
            query_run.mark_complete(result_count=len(api_results))

            logger.info("Auto-ingest %s completed: %d results", job_id, len(api_results))

        except Exception as e:
            logger.exception("Auto-ingest %s failed: %s", job_id, e)
            query_run.mark_complete(result_count=0, error=str(e))

    return {'status': 'completed', 'keywords': len(keywords)}


@shared_task
def cleanup_stale_jobs():
    """
    Clean up jobs stuck in running state.

    This runs every 5 minutes and marks jobs as failed if they've been
    running longer than the stale threshold (default 30 minutes).
    """
    threshold = timezone.now() - timedelta(minutes=settings.JOB_STALE_THRESHOLD_MINUTES)

    stale_jobs = QueryRun.objects.filter(
        state__in=[QueryRun.State.PENDING, QueryRun.State.QUEUED, QueryRun.State.RUNNING],
        started_at__lt=threshold
    )

    count = 0
    for job in stale_jobs:
        logger.warning("Marking stale job %s as failed (started %s)", job.job_id, job.started_at)
        job.mark_complete(
            result_count=job.found_count or 0,
            error='Job stuck in running state, marked as failed by cleanup'
        )
        count += 1

    if count:
        logger.info("Cleanup marked %d stale jobs as failed", count)

    return {'cleaned': count}


# Priority for retried searches (between user=0 and auto=9)
PRIORITY_RETRY = 5


MAX_RETRY_ATTEMPTS = 3  # Maximum number of retry attempts per job


@shared_task
def retry_errored_searches():
    """
    Re-queue errored user searches with medium priority.

    Runs every 10 minutes. Finds errored SUB_SEARCH jobs and re-queues them
    with priority 5 (between user priority 0 and auto priority 9).
    Only retries jobs that haven't exceeded MAX_RETRY_ATTEMPTS.
    """
    # Find errored user searches from the last 24 hours that haven't been retried too many times
    cutoff = timezone.now() - timedelta(hours=24)

    errored_jobs = QueryRun.objects.filter(
        source=QueryRun.Source.SUB_SEARCH,
        state=QueryRun.State.ERROR,
        completed_at__gte=cutoff,
        retry_count__lt=MAX_RETRY_ATTEMPTS,  # Only retry jobs under the limit
    ).exclude(
        error__icontains='stopped by user'  # Don't retry user-stopped jobs
    ).exclude(
        error__icontains='retried as'  # Don't retry jobs that already spawned a retry
    ).order_by('started_at')[:10]  # Limit to 10 retries per run

    retried = 0
    for job in errored_jobs:
        # Create a new job with the same parameters
        new_job_id = uuid.uuid4().hex
        new_retry_count = job.retry_count + 1

        new_job = QueryRun.objects.create(
            job_id=new_job_id,
            source=QueryRun.Source.SUB_SEARCH,
            state=QueryRun.State.QUEUED,
            keyword=job.keyword,
            limit_value=job.limit_value,
            unmoderated_only=job.unmoderated_only,
            exclude_nsfw=job.exclude_nsfw,
            min_subscribers=job.min_subscribers,
            activity_mode=job.activity_mode,
            activity_threshold_utc=job.activity_threshold_utc,
            priority=PRIORITY_RETRY,
            notification_email=job.notification_email,
            retry_count=new_retry_count,
            retried_from_job_id=job.job_id,
        )

        # Mark old job as superseded (update error message)
        job.error = f"{job.error} (retried as {new_job_id})"
        job.save(update_fields=['error'])

        # Submit with medium priority
        task = run_sub_search.apply_async(
            args=[new_job_id],
            priority=PRIORITY_RETRY,
        )

        new_job.celery_task_id = task.id
        new_job.save(update_fields=['celery_task_id'])

        logger.info("Retried errored search %s -> %s (keyword=%s, attempt=%d/%d)",
                   job.job_id, new_job_id, job.keyword, new_retry_count, MAX_RETRY_ATTEMPTS)
        retried += 1

    if retried:
        logger.info("Retry task re-queued %d errored searches", retried)

    return {'retried': retried}


@shared_task
def check_idle_and_run_random():
    """
    Check if queue is idle and run a random search if no search completed recently.

    Runs every minute. If no search has completed in the last 7 minutes and
    the queue is empty, triggers a random search.
    """
    # Check if anything is currently running or queued
    active_jobs = QueryRun.objects.filter(
        state__in=[QueryRun.State.PENDING, QueryRun.State.QUEUED, QueryRun.State.RUNNING]
    ).exists()

    if active_jobs:
        # Queue is not idle, do nothing
        return {'status': 'busy', 'triggered': False}

    # Check when the last search completed (including errors - they count as activity)
    idle_threshold = timezone.now() - timedelta(minutes=7)

    # Consider COMPLETE, ERROR, and STOPPED states as "finished" activity
    last_finished = QueryRun.objects.filter(
        state__in=[QueryRun.State.COMPLETE, QueryRun.State.ERROR, QueryRun.State.STOPPED],
        completed_at__isnull=False
    ).order_by('-completed_at').first()

    if last_finished and last_finished.completed_at > idle_threshold:
        # A search finished within the last 7 minutes, don't trigger yet
        return {'status': 'recent_activity', 'triggered': False}

    # Queue is empty and idle for 7+ minutes, trigger a random search
    logger.info("Queue idle for 7+ minutes, triggering random search")
    run_random_search.apply_async(priority=PRIORITY_AUTO, queue='search')

    return {'status': 'triggered', 'triggered': True}


@shared_task
def cleanup_broken_nodes():
    """
    Remove nodes that have been broken for too long.
    """
    from nodes.models import VolunteerNode

    threshold = timezone.now() - timedelta(days=settings.NODE_BROKEN_RETENTION_DAYS)

    broken_nodes = VolunteerNode.objects.filter(
        is_deleted=False,
        health_status=VolunteerNode.HealthStatus.BROKEN,
        broken_since__lt=threshold
    )

    count = broken_nodes.count()
    for node in broken_nodes:
        node.soft_delete()
        logger.info("Removed broken node: %s", node.reddit_username or node.email)

    if count:
        logger.info("Cleanup removed %d broken nodes", count)

    return {'removed': count}


@shared_task
def refresh_rolling_stats():
    """
    Refresh 24-hour rolling statistics.

    Runs every 15 minutes at :00, :15, :30, :45 via Celery Beat.
    """
    from .models import RollingStats

    stats = RollingStats.refresh_stats()
    logger.info(
        "Refreshed rolling stats: discovered=%d, updated=%d, human=%d, bot=%d",
        stats.subs_discovered_24h,
        stats.subs_updated_24h,
        stats.human_searches_24h,
        stats.bot_searches_24h,
    )
    return stats.to_dict()


def _fetch_random_keyword():
    """Fetch a random word from API or use fallback."""
    DEFAULT_WORDS = [
        "atlas", "harbor", "mosaic", "cocoa", "summit",
        "glow", "orbit", "quartz", "tango", "whistle",
    ]

    try:
        response = requests.get(settings.RANDOM_WORD_API, timeout=5)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list) and data:
            return re.sub(r'[^A-Za-z ]', '', data[0]).strip().lower()
        if isinstance(data, str):
            return re.sub(r'[^A-Za-z ]', '', data).strip().lower()
    except Exception:
        logger.debug("Random word fetch failed", exc_info=True)

    return random.choice(DEFAULT_WORDS)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_completion_notification(self, job_id: str):
    """
    Send email notification when a search job completes.

    This task is called after a job finishes if the user provided an email.
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    try:
        query_run = QueryRun.objects.get(job_id=job_id)
    except QueryRun.DoesNotExist:
        logger.error("Job %s not found for email notification", job_id)
        return {'error': 'Job not found'}

    if not query_run.notification_email:
        logger.debug("No notification email for job %s", job_id)
        return {'skipped': True}

    # Check if email settings are configured
    smtp_host = getattr(settings, 'NODE_EMAIL_SMTP_HOST', '')
    smtp_port = getattr(settings, 'NODE_EMAIL_SMTP_PORT', 587)
    smtp_user = getattr(settings, 'NODE_EMAIL_SMTP_USERNAME', '')
    smtp_pass = getattr(settings, 'NODE_EMAIL_SMTP_PASSWORD', '')
    sender_email = getattr(settings, 'NODE_EMAIL_SENDER', '')
    sender_name = getattr(settings, 'NODE_EMAIL_SENDER_NAME', 'Sub Search')
    use_tls = getattr(settings, 'NODE_EMAIL_USE_TLS', True)

    if not all([smtp_host, smtp_user, smtp_pass, sender_email]):
        logger.warning("Email not configured, skipping notification for job %s", job_id)
        return {'skipped': True, 'reason': 'Email not configured'}

    # Build the results URL
    site_url = getattr(settings, 'SITE_URL', '').rstrip('/')
    if not site_url:
        site_url = 'http://localhost:8000'

    results_url = f"{site_url}/all-the-subs?job_id={job_id}"
    download_url = f"{site_url}/job/{job_id}/download.csv"

    # Determine status
    if query_run.state == QueryRun.State.COMPLETE:
        status_text = "completed successfully"
        status_emoji = "✅"
    elif query_run.state == QueryRun.State.STOPPED:
        status_text = "was stopped"
        status_emoji = "⏹️"
    else:
        status_text = "encountered an error"
        status_emoji = "❌"

    keyword_display = query_run.keyword or "all subreddits"

    # Create email message
    subject = f"{status_emoji} Sub Search Complete: {keyword_display}"

    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }}
        .container {{ max-width: 600px; margin: 0 auto; background: #1e293b; border-radius: 16px; padding: 32px; }}
        h1 {{ color: #22d3ee; margin-top: 0; }}
        .stats {{ background: #334155; border-radius: 12px; padding: 20px; margin: 20px 0; }}
        .stat {{ display: inline-block; margin-right: 30px; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #22d3ee; }}
        .stat-label {{ font-size: 12px; text-transform: uppercase; color: #94a3b8; }}
        .btn {{ display: inline-block; background: linear-gradient(to right, #22d3ee, #a78bfa); color: #0f172a; padding: 12px 24px; border-radius: 12px; text-decoration: none; font-weight: 600; margin-right: 10px; margin-top: 10px; }}
        .btn-secondary {{ background: #334155; color: #e2e8f0; }}
        .error {{ color: #f87171; margin-top: 10px; }}
        .footer {{ margin-top: 30px; font-size: 12px; color: #64748b; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{status_emoji} Your Sub Search {status_text}</h1>
        <p>Your search for "<strong>{keyword_display}</strong>" has finished.</p>

        <div class="stats">
            <div class="stat">
                <div class="stat-value">{query_run.result_count:,}</div>
                <div class="stat-label">Subreddits Found</div>
            </div>
            <div class="stat">
                <div class="stat-value">{query_run.checked_count:,}</div>
                <div class="stat-label">Checked</div>
            </div>
        </div>

        {"<p class='error'>Error: " + query_run.error + "</p>" if query_run.error else ""}

        <p>
            <a href="{results_url}" class="btn">View Results</a>
            <a href="{download_url}" class="btn btn-secondary">Download CSV</a>
        </p>

        <div class="footer">
            <p>This email was sent because you requested a notification when your Sub Search completed.</p>
            <p>— <a href="{site_url}" style="color: #22d3ee;">Sub Search</a></p>
        </div>
    </div>
</body>
</html>
"""

    text_body = f"""
Your Sub Search {status_text}!

Search: {keyword_display}
Results: {query_run.result_count:,} subreddits found
Checked: {query_run.checked_count:,}
{f"Error: {query_run.error}" if query_run.error else ""}

View results: {results_url}
Download CSV: {download_url}

— Sub Search
{site_url}
"""

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = f"{sender_name} <{sender_email}>"
    msg['To'] = query_run.notification_email

    msg.attach(MIMEText(text_body, 'plain'))
    msg.attach(MIMEText(html_body, 'html'))

    try:
        if use_tls:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port)

        server.login(smtp_user, smtp_pass)
        server.sendmail(sender_email, [query_run.notification_email], msg.as_string())
        server.quit()

        logger.info("Sent completion notification for job %s to %s", job_id, query_run.notification_email)
        return {'sent': True, 'to': query_run.notification_email}

    except Exception as e:
        logger.exception("Failed to send notification email for job %s: %s", job_id, e)
        raise self.retry(exc=e)


def submit_user_search(
    keyword=None,
    limit=1000,
    unmoderated_only=False,
    exclude_nsfw=False,
    min_subs=0,
    activity_mode='any',
    activity_threshold_utc=None,
    notification_email=None,
):
    """
    Submit a user search job with HIGH priority.

    Returns the job_id which can be used to track progress.
    """
    job_id = uuid.uuid4().hex

    query_run = QueryRun.objects.create(
        job_id=job_id,
        source=QueryRun.Source.SUB_SEARCH,
        state=QueryRun.State.QUEUED,
        keyword=keyword,
        limit_value=min(limit, settings.PUBLIC_API_LIMIT_CAP),
        unmoderated_only=unmoderated_only,
        exclude_nsfw=exclude_nsfw,
        min_subscribers=min_subs,
        activity_mode=activity_mode,
        activity_threshold_utc=activity_threshold_utc,
        priority=PRIORITY_USER,
        notification_email=notification_email,
    )

    # Submit task with high priority (lower number = higher priority)
    task = run_sub_search.apply_async(
        args=[job_id],
        priority=PRIORITY_USER,
    )

    # Update with task ID
    query_run.celery_task_id = task.id
    query_run.save(update_fields=['celery_task_id'])

    logger.info("Submitted user search: job_id=%s keyword=%r task_id=%s", job_id, keyword, task.id)

    return job_id
