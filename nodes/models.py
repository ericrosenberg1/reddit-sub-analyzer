"""
Django models for Volunteer Nodes.
"""

import secrets
from django.db import models
from django.utils import timezone


class VolunteerNode(models.Model):
    """
    Tracks volunteer node registrations for distributed crawling.
    """
    class HealthStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACTIVE = 'active', 'Active'
        BROKEN = 'broken', 'Broken'

    email = models.EmailField(max_length=256)
    reddit_username = models.CharField(max_length=256, null=True, blank=True)
    location = models.CharField(max_length=256, null=True, blank=True)
    system_details = models.CharField(max_length=512, null=True, blank=True)
    availability = models.CharField(max_length=256, null=True, blank=True)
    bandwidth_notes = models.CharField(max_length=256, null=True, blank=True)
    notes = models.TextField(max_length=1000, null=True, blank=True)

    health_status = models.CharField(
        max_length=32,
        choices=HealthStatus.choices,
        default=HealthStatus.PENDING,
        db_index=True
    )
    last_check_in_at = models.DateTimeField(null=True, blank=True)
    broken_since = models.DateTimeField(null=True, blank=True)

    manage_token = models.CharField(max_length=64, unique=True, db_index=True)
    manage_token_sent_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['health_status', '-updated_at']),
        ]

    def __str__(self):
        return f"{self.reddit_username or self.email} ({self.health_status})"

    def save(self, *args, **kwargs):
        if not self.manage_token:
            self.manage_token = secrets.token_urlsafe(32)
        if not self.last_check_in_at:
            self.last_check_in_at = timezone.now()
        super().save(*args, **kwargs)

    def soft_delete(self):
        """Soft delete the node."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=['is_deleted', 'deleted_at', 'updated_at'])

    def mark_broken(self):
        """Mark the node as broken."""
        if self.health_status != self.HealthStatus.BROKEN:
            self.health_status = self.HealthStatus.BROKEN
            self.broken_since = timezone.now()
            self.save(update_fields=['health_status', 'broken_since', 'updated_at'])

    def mark_active(self):
        """Mark the node as active."""
        self.health_status = self.HealthStatus.ACTIVE
        self.broken_since = None
        self.last_check_in_at = timezone.now()
        self.save(update_fields=['health_status', 'broken_since', 'last_check_in_at', 'updated_at'])

    def to_public_dict(self):
        """Return public-facing information (no email or token)."""
        return {
            'reddit_username': self.reddit_username,
            'location': self.location,
            'system_details': self.system_details,
            'availability': self.availability,
            'bandwidth_notes': self.bandwidth_notes,
            'notes': self.notes,
            'health_status': self.health_status,
            'last_check_in_at': self.last_check_in_at.isoformat() if self.last_check_in_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def get_active_nodes(cls, limit=12):
        """Get active/pending nodes for public display."""
        return cls.objects.filter(
            is_deleted=False
        ).exclude(
            health_status=cls.HealthStatus.BROKEN
        ).order_by('-updated_at')[:limit]

    @classmethod
    def get_stats(cls):
        """Get node statistics."""
        qs = cls.objects.filter(is_deleted=False)
        return {
            'total': qs.count(),
            'active': qs.filter(health_status=cls.HealthStatus.ACTIVE).count(),
            'pending': qs.filter(health_status=cls.HealthStatus.PENDING).count(),
            'broken': qs.filter(health_status=cls.HealthStatus.BROKEN).count(),
        }
