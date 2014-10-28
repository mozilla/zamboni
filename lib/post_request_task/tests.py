from django.core.signals import request_finished
from django.test import TestCase

from celery.signals import task_postrun
from mock import Mock, patch
from nose.tools import eq_

from lib.post_request_task.task import task, _get_task_queue, _discard_tasks


task_mock = Mock()


@task
def test_task():
    task_mock()


class TestTask(TestCase):

    def setUp(self):
        super(TestTask, self).setUp()
        task_mock.reset_mock()
        _discard_tasks()

    def tearDown(self):
        task_mock.reset_mock()
        _discard_tasks()
        super(TestTask, self).tearDown()

    def _verify_task_filled(self):
        queue = _get_task_queue()
        size = len(queue)
        eq_(size, 1, 'Expected 1 task in the queue, found %d' % size)
        cls, args, kwargs = queue[0]
        eq_(cls.name,
            '%s.%s' % (test_task.__module__, test_task.__name__),
            'Expected the test task, found %s' % cls.name)

    def _verify_task_empty(self):
        assert len(_get_task_queue()) == 0, (
            'Expected empty queue, got %s: %s' % (len(_get_task_queue()),
                                                  _get_task_queue()))

    def test_task(self):
        test_task.delay()
        assert not task_mock.called

    @patch('lib.post_request_task.task.PostRequestTask.original_apply_async')
    def test_task_postrun(self, _mock):
        with self.settings(CELERY_ALWAYS_EAGER=False):
            test_task.delay()
        self._verify_task_filled()

        task_postrun.send(sender=self)
        self._verify_task_empty()

        # Assert the original `apply_async` called.
        assert _mock.called, (
            'Expected PostRequestTask.original_apply_async call')

    @patch('lib.post_request_task.task.PostRequestTask.original_apply_async')
    def test_request_finished(self, _mock):
        with self.settings(CELERY_ALWAYS_EAGER=False):
            test_task.delay()
        self._verify_task_filled()

        request_finished.send(sender=self)
        self._verify_task_empty()

        # Assert the original `apply_async` called.
        assert _mock.called, (
            'Expected PostRequestTask.original_apply_async call')

    @patch('lib.post_request_task.task.PostRequestTask.original_apply_async')
    def test_request_failed(self, _mock):
        with self.settings(CELERY_ALWAYS_EAGER=False):
            test_task.delay()
        self._verify_task_filled()

        # Simulate a request exception.
        _discard_tasks()
        self._verify_task_empty()

        # Assert the original `apply_async` was not called.
        assert not _mock.called, (
            'Unexpected PostRequestTask.original_apply_async call')

    def test_deduplication(self):
        """Test the same task added multiple times is de-duped."""
        with self.settings(CELERY_ALWAYS_EAGER=False):
            test_task.delay()
            test_task.delay()

        self._verify_task_filled()
