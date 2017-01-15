"""Execute Moya logic asyncronously."""

from __future__ import print_function
from __future__ import unicode_literals

import logging
from threading import Thread, Event
from queue import Queue

from . import logic


log = logging.getLogger('moya.runtime')


class ExecutorJob(object):
    """A single execution pipeline."""

    def __init__(self, archive, context, root_node):
        self.done_event = Event()
        self._exception = None
        self._logic_generator = logic._logic_loop(context, [root_node])
        self._next = self._logic_generator.next

    def __iter__(self):
        """Make object an iterator."""
        return self

    def next(self):
        """Run the next element."""
        try:
            self._next()
        except StopIteration:
            self.done_event.set()
            return None
        except Exception as e:
            self._exception = e
            self.done_event.set()
            return None
        else:
            return self

    def wait(self):
        """Wait for job to finish."""
        self.done_event.wait()
        if self._exception is not None:
            raise self._exception


class Executor(object):
    """Main logic executor."""

    def __init__(self, max_threads=10):
        self.max_threads = max_threads
        self.queue = Queue()
        self.threads = set()
        self.thread_index = 1
        self._create_workers()
        self._start_workers()

    def __del__(self):
        """Stop workers when executor goes out of scope."""
        self.close()

    def _create_workers(self):
        """Create initial threads."""
        for _ in range(self.max_threads):
            self._create_worker(self.thread_index)
            self.thread_index += 1

    def _create_worker(self, index):
        name = "ExecutorThread-{}".format(index)
        thread = ExecutorWorkerThread(self, name)
        self.threads.add(thread)

    def _start_workers(self):
        for thread in self.threads:
            thread.start()

    def _destroy_workers(self):
        for thread in self.threads:
            self.queue.put(None)
        self.threads.clear()

    def close(self):
        self._destroy_workers()

    def execute(self, archive, context, root_node):
        executor_job = ExecutorJob(archive, context, root_node)
        self.queue.put(executor_job)
        return executor_job


class ExecutorWorkerThread(Thread):
    """Executes jobs, one tag at a time."""

    def __init__(self, executor, name):
        super(ExecutorWorkerThread, self).__init__(name=name,
                                                   target=self.execute_loop,
                                                   args=(executor,))

    def execute_loop(self, executor):
        queue = executor.queue
        get = queue.get
        put = queue.put
        empty = queue.empty
        while 1:
            job = get()
            if job is None:
                break
            _next = job.next
            while _next():
                if empty():
                    continue
                put(job)
                break
