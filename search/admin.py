"""
Django admin configuration for search app.
"""

from django.contrib import admin
from .models import QueryRun, Subreddit


@admin.register(QueryRun)
class QueryRunAdmin(admin.ModelAdmin):
    list_display = ['job_id', 'source', 'state', 'keyword', 'result_count', 'started_at', 'completed_at']
    list_filter = ['source', 'state', 'started_at']
    search_fields = ['job_id', 'keyword']
    readonly_fields = ['job_id', 'celery_task_id', 'started_at', 'completed_at', 'duration_ms']
    ordering = ['-started_at']


@admin.register(Subreddit)
class SubredditAdmin(admin.ModelAdmin):
    list_display = ['name', 'subscribers', 'is_unmoderated', 'is_nsfw', 'mod_count', 'updated_at']
    list_filter = ['is_unmoderated', 'is_nsfw', 'source']
    search_fields = ['name', 'display_name_prefixed', 'title']
    readonly_fields = ['first_seen_at', 'updated_at']
    ordering = ['-subscribers']
