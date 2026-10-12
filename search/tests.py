from unittest import mock

from django.test import TestCase

from . import tasks
from .models import QueryRun


class FindUnmoderatedSubredditsTests(TestCase):
    """Every task reads payload['results'], ['evaluated'] or ['checked'] directly,
    so include_all=True must always return the dict shape."""

    @mock.patch('praw.Reddit')
    def test_include_all_returns_dict_with_counts(self, reddit_cls):
        reddit_cls.return_value.subreddits.new.return_value = []

        payload = tasks.find_unmoderated_subreddits(limit=5, include_all=True)

        self.assertEqual(payload, {'results': [], 'evaluated': [], 'checked': 0})


class RunSubSearchTests(TestCase):
    def test_returns_checked_count_from_search_payload(self):
        QueryRun.objects.create(job_id='job-1', keyword='python', limit_value=10)
        payload = {'results': [], 'evaluated': [{'name': 'a'}, {'name': 'b'}], 'checked': 42}

        with mock.patch.object(tasks, 'find_unmoderated_subreddits', return_value=payload) as search:
            result = tasks.run_sub_search('job-1')

        self.assertTrue(search.call_args.kwargs['include_all'])
        self.assertEqual(result, {'job_id': 'job-1', 'result_count': 0, 'checked': 42})
        run = QueryRun.objects.get(job_id='job-1')
        self.assertEqual(run.state, QueryRun.State.COMPLETE)
        self.assertIsNone(run.error)
