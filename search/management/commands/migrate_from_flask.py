"""
Management command to migrate data from the Flask SQLite database to Django.

This command is useful when transitioning from the Flask version to Django.
It reads from the existing SQLite database and imports all data into Django models.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from search.models import QueryRun, Subreddit
from nodes.models import VolunteerNode


class Command(BaseCommand):
    help = 'Migrate data from Flask SQLite database to Django models'

    def add_arguments(self, parser):
        parser.add_argument(
            '--db-path',
            type=str,
            default=str(Path(settings.BASE_DIR) / 'data' / 'subsearch.db'),
            help='Path to the Flask SQLite database'
        )
        parser.add_argument(
            '--skip-subreddits',
            action='store_true',
            help='Skip migrating subreddits (useful for large databases)'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Batch size for subreddit migration'
        )

    def handle(self, *args, **options):
        db_path = options['db_path']

        if not Path(db_path).exists():
            raise CommandError(f"Database file not found: {db_path}")

        self.stdout.write(f"Connecting to Flask database: {db_path}")

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Migrate query_runs
        self.stdout.write("Migrating query runs...")
        self._migrate_query_runs(cursor)

        # Migrate subreddits
        if not options['skip_subreddits']:
            self.stdout.write("Migrating subreddits...")
            self._migrate_subreddits(cursor, options['batch_size'])
        else:
            self.stdout.write("Skipping subreddits (--skip-subreddits)")

        # Migrate volunteer nodes
        self.stdout.write("Migrating volunteer nodes...")
        self._migrate_volunteer_nodes(cursor)

        conn.close()
        self.stdout.write(self.style.SUCCESS("Migration complete!"))

    def _migrate_query_runs(self, cursor):
        cursor.execute("SELECT * FROM query_runs ORDER BY id")
        rows = cursor.fetchall()

        count = 0
        for row in rows:
            job_id = row['job_id']
            if QueryRun.objects.filter(job_id=job_id).exists():
                continue

            QueryRun.objects.create(
                job_id=job_id,
                source=row['source'] or 'manual',
                state='complete' if row['completed_at'] else 'error',
                started_at=self._parse_datetime(row['started_at']),
                completed_at=self._parse_datetime(row['completed_at']),
                keyword=row['keyword'],
                limit_value=row['limit_value'],
                unmoderated_only=bool(row['unmoderated_only']),
                exclude_nsfw=bool(row['exclude_nsfw']),
                min_subscribers=row['min_subscribers'] or 0,
                activity_mode=row['activity_mode'],
                activity_threshold_utc=row['activity_threshold_utc'],
                file_name=row['file_name'],
                result_count=row['result_count'] or 0,
                duration_ms=row['duration_ms'],
                error=row['error'],
            )
            count += 1

        self.stdout.write(f"  Migrated {count} query runs")

    def _migrate_subreddits(self, cursor, batch_size):
        cursor.execute("SELECT COUNT(*) FROM subreddits")
        total = cursor.fetchone()[0]
        self.stdout.write(f"  Total subreddits to migrate: {total}")

        offset = 0
        while offset < total:
            cursor.execute(
                "SELECT * FROM subreddits ORDER BY id LIMIT ? OFFSET ?",
                (batch_size, offset)
            )
            rows = cursor.fetchall()

            with transaction.atomic():
                for row in rows:
                    name = row['name']
                    if not name or Subreddit.objects.filter(name__iexact=name).exists():
                        continue

                    Subreddit.objects.create(
                        name=name,
                        display_name_prefixed=row['display_name_prefixed'] or f"r/{name}",
                        title=row['title'],
                        public_description=row['public_description'],
                        url=row['url'],
                        subscribers=row['subscribers'],
                        is_unmoderated=bool(row['is_unmoderated']),
                        is_nsfw=bool(row['is_nsfw']),
                        last_activity_utc=row['last_activity_utc'],
                        mod_count=row['mod_count'],
                        last_keyword=row['last_keyword'],
                        source=row['source'],
                    )

            offset += batch_size
            self.stdout.write(f"  Processed {min(offset, total)}/{total} subreddits")

    def _migrate_volunteer_nodes(self, cursor):
        try:
            cursor.execute("SELECT * FROM volunteer_nodes ORDER BY id")
            rows = cursor.fetchall()
        except sqlite3.OperationalError:
            self.stdout.write("  No volunteer_nodes table found, skipping")
            return

        count = 0
        for row in rows:
            token = row['manage_token']
            if VolunteerNode.objects.filter(manage_token=token).exists():
                continue

            VolunteerNode.objects.create(
                email=row['email'],
                reddit_username=row['reddit_username'],
                location=row['location'],
                system_details=row['system_details'],
                availability=row['availability'],
                bandwidth_notes=row['bandwidth_notes'],
                notes=row['notes'],
                health_status=row['health_status'] or 'pending',
                last_check_in_at=self._parse_datetime(row['last_check_in_at']),
                broken_since=self._parse_datetime(row['broken_since']),
                manage_token=token,
                manage_token_sent_at=self._parse_datetime(row['manage_token_sent_at']),
                is_deleted=bool(row['is_deleted']),
                deleted_at=self._parse_datetime(row['deleted_at']),
            )
            count += 1

        self.stdout.write(f"  Migrated {count} volunteer nodes")

    def _parse_datetime(self, value):
        if not value:
            return None
        try:
            if isinstance(value, datetime):
                return timezone.make_aware(value) if timezone.is_naive(value) else value
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return timezone.make_aware(dt) if timezone.is_naive(dt) else dt
        except (ValueError, TypeError):
            return None
