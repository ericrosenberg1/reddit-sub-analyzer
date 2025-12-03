"""
Django models for Reddit Sub Analyzer.
"""

from django.db import models
from django.utils import timezone


class QueryRun(models.Model):
    """
    Tracks each search job execution.
    """
    class Source(models.TextChoices):
        MANUAL = 'manual', 'Manual'
        SUB_SEARCH = 'sub_search', 'Sub Search'
        AUTO_INGEST = 'auto-ingest', 'Auto Ingest'
        AUTO_RANDOM = 'auto-random', 'Auto Random'

    class State(models.TextChoices):
        PENDING = 'pending', 'Pending'
        QUEUED = 'queued', 'Queued'
        RUNNING = 'running', 'Running'
        COMPLETE = 'complete', 'Complete'
        STOPPED = 'stopped', 'Stopped'
        ERROR = 'error', 'Error'

    job_id = models.CharField(max_length=64, unique=True, db_index=True)
    source = models.CharField(max_length=64, choices=Source.choices, default=Source.MANUAL)
    state = models.CharField(max_length=32, choices=State.choices, default=State.PENDING)

    # Timestamps
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Search parameters
    keyword = models.CharField(max_length=128, null=True, blank=True)
    limit_value = models.IntegerField(null=True, blank=True)
    unmoderated_only = models.BooleanField(default=False)
    exclude_nsfw = models.BooleanField(default=False)
    min_subscribers = models.IntegerField(default=0)
    activity_mode = models.CharField(max_length=32, null=True, blank=True)
    activity_threshold_utc = models.BigIntegerField(null=True, blank=True)

    # Results
    file_name = models.CharField(max_length=256, null=True, blank=True)
    result_count = models.IntegerField(default=0)
    duration_ms = models.IntegerField(null=True, blank=True)
    error = models.TextField(null=True, blank=True)

    # Celery task tracking
    celery_task_id = models.CharField(max_length=256, null=True, blank=True, db_index=True)

    # Progress tracking (for real-time updates)
    checked_count = models.IntegerField(default=0)
    found_count = models.IntegerField(default=0)
    progress_phase = models.CharField(max_length=32, default='queued')

    # Priority (0 = highest/user, 9 = lowest/automated)
    priority = models.IntegerField(default=0)

    # Optional email notification when search completes
    notification_email = models.EmailField(max_length=256, null=True, blank=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [
            models.Index(fields=['source', '-started_at']),
            models.Index(fields=['state', '-started_at']),
            models.Index(fields=['celery_task_id']),
        ]

    def __str__(self):
        return f"{self.job_id} ({self.source})"

    @property
    def is_running(self):
        return self.state in (self.State.PENDING, self.State.QUEUED, self.State.RUNNING)

    @property
    def is_complete(self):
        return self.state in (self.State.COMPLETE, self.State.STOPPED, self.State.ERROR)

    def mark_running(self):
        """Mark the job as running."""
        self.state = self.State.RUNNING
        self.started_at = timezone.now()
        self.progress_phase = 'running'
        self.save(update_fields=['state', 'started_at', 'progress_phase'])

    def mark_complete(self, result_count=0, error=None):
        """Mark the job as complete."""
        self.completed_at = timezone.now()
        self.result_count = result_count
        self.error = error

        if error:
            self.state = self.State.ERROR
        else:
            self.state = self.State.COMPLETE

        if self.started_at:
            delta = self.completed_at - self.started_at
            self.duration_ms = int(delta.total_seconds() * 1000)

        self.save(update_fields=[
            'state', 'completed_at', 'result_count', 'error', 'duration_ms'
        ])

    def mark_stopped(self):
        """Mark the job as stopped by user."""
        self.state = self.State.STOPPED
        self.completed_at = timezone.now()
        self.error = 'Stopped by user'
        self.save(update_fields=['state', 'completed_at', 'error'])

    def update_progress(self, checked=None, found=None, phase=None):
        """Update progress counters."""
        update_fields = []
        if checked is not None:
            self.checked_count = checked
            update_fields.append('checked_count')
        if found is not None:
            self.found_count = found
            update_fields.append('found_count')
        if phase is not None:
            self.progress_phase = phase
            update_fields.append('progress_phase')
        if update_fields:
            self.save(update_fields=update_fields)

    def to_status_dict(self):
        """Return a dictionary for the status API endpoint."""
        return {
            'job_id': self.job_id,
            'source': self.source,
            'state': self.state,
            'keyword': self.keyword,
            'limit': self.limit_value,
            'checked': self.checked_count,
            'found': self.found_count,
            'done': self.is_complete,
            'error': self.error,
            'results_ready': self.state == self.State.COMPLETE,
            'result_count': self.result_count,
            'progress_phase': self.progress_phase,
            'priority': self.priority,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }


class Subreddit(models.Model):
    """
    Subreddit metadata storage.
    """
    name = models.CharField(max_length=128, unique=True, db_index=True)
    display_name_prefixed = models.CharField(max_length=140, null=True, blank=True)
    title = models.CharField(max_length=512, null=True, blank=True)
    public_description = models.TextField(null=True, blank=True)
    url = models.URLField(max_length=256, null=True, blank=True)

    subscribers = models.IntegerField(null=True, blank=True, db_index=True)
    is_unmoderated = models.BooleanField(default=False, db_index=True)
    is_nsfw = models.BooleanField(default=False)

    last_activity_utc = models.BigIntegerField(null=True, blank=True)
    mod_count = models.IntegerField(null=True, blank=True)

    # Tracking
    last_seen_run = models.ForeignKey(
        QueryRun,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subreddits'
    )
    last_keyword = models.CharField(max_length=128, null=True, blank=True)
    source = models.CharField(max_length=64, null=True, blank=True)

    first_seen_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ['-subscribers']
        indexes = [
            models.Index(fields=['is_unmoderated', '-subscribers']),
            models.Index(fields=['-updated_at']),
            models.Index(fields=['is_nsfw', '-subscribers']),
            models.Index(fields=['last_seen_run', '-subscribers']),
        ]

    def __str__(self):
        return self.display_name_prefixed or f"r/{self.name}"

    def to_dict(self):
        """Return a dictionary representation for API responses."""
        return {
            'name': self.name,
            'display_name_prefixed': self.display_name_prefixed,
            'title': self.title,
            'public_description': self.public_description,
            'url': self.url,
            'subscribers': self.subscribers,
            'is_unmoderated': self.is_unmoderated,
            'is_nsfw': self.is_nsfw,
            'last_activity_utc': self.last_activity_utc,
            'mod_count': self.mod_count,
            'source': self.source,
            'first_seen_at': self.first_seen_at.isoformat() if self.first_seen_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def upsert_from_dict(cls, data, query_run=None, keyword=None, source=None):
        """
        Create or update a subreddit from a dictionary.
        Returns the subreddit instance.
        """
        name = (data.get('name') or '').strip()
        if not name:
            return None

        defaults = {
            'display_name_prefixed': data.get('display_name_prefixed') or f"r/{name}",
            'title': data.get('title') or name,
            'public_description': data.get('public_description') or '',
            'url': data.get('url'),
            'subscribers': int(data.get('subscribers') or 0),
            'is_unmoderated': bool(data.get('is_unmoderated')),
            'is_nsfw': bool(data.get('is_nsfw')),
            'last_activity_utc': data.get('last_activity_utc'),
            'mod_count': data.get('mod_count'),
            'last_keyword': (data.get('keyword') or keyword or '')[:128],
            'source': (data.get('source') or source or 'manual')[:64],
        }

        if query_run:
            defaults['last_seen_run'] = query_run

        sub, created = cls.objects.update_or_create(
            name__iexact=name,
            defaults=defaults
        )
        return sub


class SummaryCache(models.Model):
    """
    Cache for summary statistics to avoid expensive aggregations.
    """
    key = models.CharField(max_length=64, primary_key=True)
    data = models.JSONField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Summary Cache'
        verbose_name_plural = 'Summary Cache'
