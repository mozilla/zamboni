import threading
from functools import partial

from django.core.signals import got_request_exception, request_finished

import commonware.log
from celery import task as base_task
from celery import Task
from celery.signals import task_postrun


log = commonware.log.getLogger('z.post_request_task')


_locals = threading.local()


def _get_task_queue():
    """Returns the calling thread's task queue."""
    return _locals.__dict__.setdefault('task_queue', [])


def _send_tasks(**kwargs):
    """Sends all delayed Celery tasks."""
    queue = _get_task_queue()
    while queue:
        cls, args, kwargs = queue.pop(0)
        cls.original_apply_async(*args, **kwargs)


def _discard_tasks(**kwargs):
    """Discards all delayed Celery tasks."""
    _get_task_queue()[:] = []


def _append_task(t):
    """Append a task to the queue.

    Expected argument is a tuple of the (task class, args, kwargs).

    This doesn't append to queue if the argument is already in the queue.

    """
    queue = _get_task_queue()
    if t not in queue:
        queue.append(t)
    else:
        log.debug('Removed duplicate task: %s' % (t,))


class PostRequestTask(Task):
    """A task whose execution is delayed until after the request finishes.

    This simply wraps celery's `@task` decorator and stores the task calls
    until after the request is finished, then fires them off.

    """
    abstract = True

    def original_apply_async(self, *args, **kwargs):
        return super(PostRequestTask, self).apply_async(*args, **kwargs)

    def apply_async(self, *args, **kwargs):
        _append_task((self, args, kwargs))


# Replacement `@task` decorator.
task = partial(base_task, base=PostRequestTask)


# Hook the signal handlers up.
# Send the tasks to celery when the request is finished.
request_finished.connect(_send_tasks,
                         dispatch_uid='request_finished_tasks')
# Also send the tasks when a task is finished (outside the request-response
# cycle, when a task calls another task).
task_postrun.connect(_send_tasks, dispatch_uid='tasks_finished_tasks')

# And make sure to discard the task queue when we have an exception in the
# request-response cycle.
got_request_exception.connect(_discard_tasks,
                              dispatch_uid='request_exception_tasks')
