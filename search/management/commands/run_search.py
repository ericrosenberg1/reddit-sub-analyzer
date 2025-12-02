"""
Management command to manually run a sub search.

This is useful for testing or running searches from the command line.
"""

from django.core.management.base import BaseCommand
from search.tasks import submit_user_search


class Command(BaseCommand):
    help = 'Run a sub search from the command line'

    def add_arguments(self, parser):
        parser.add_argument(
            'keyword',
            type=str,
            nargs='?',
            default=None,
            help='Keyword to search for (optional)'
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=1000,
            help='Maximum subreddits to check'
        )
        parser.add_argument(
            '--unmoderated',
            action='store_true',
            help='Only show unmoderated subreddits'
        )
        parser.add_argument(
            '--exclude-nsfw',
            action='store_true',
            help='Exclude NSFW subreddits'
        )
        parser.add_argument(
            '--min-subscribers',
            type=int,
            default=0,
            help='Minimum subscriber count'
        )

    def handle(self, *args, **options):
        job_id = submit_user_search(
            keyword=options['keyword'],
            limit=options['limit'],
            unmoderated_only=options['unmoderated'],
            exclude_nsfw=options['exclude_nsfw'],
            min_subs=options['min_subscribers'],
        )

        self.stdout.write(f"Search job submitted: {job_id}")
        self.stdout.write("Run 'celery -A reddit_analyzer worker -l info' to process the job")
