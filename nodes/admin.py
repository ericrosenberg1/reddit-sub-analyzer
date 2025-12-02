"""
Django admin configuration for nodes app.
"""

from django.contrib import admin
from .models import VolunteerNode


@admin.register(VolunteerNode)
class VolunteerNodeAdmin(admin.ModelAdmin):
    list_display = ['reddit_username', 'email', 'health_status', 'location', 'last_check_in_at', 'is_deleted']
    list_filter = ['health_status', 'is_deleted', 'created_at']
    search_fields = ['reddit_username', 'email', 'location']
    readonly_fields = ['manage_token', 'created_at', 'updated_at', 'deleted_at']
    ordering = ['-updated_at']
