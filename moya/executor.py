from __future__ import unicode_literals
from __future__ import print_function


from threading import Thread, Queue, Event


class ExecutorJob(object):
    def __init__(self, archive, context, root_node):
        self.archive = archive
        self.context = context
        self.node = root_node
        self.done_event = Event

    def wait(self):
        self.done_event.wait()


class Executor(Thread):
    """Main logic executor."""

    def __init__(self, max_threads=10):
        self.max_threads = max_threads
        self.process_queue = Queue()
        self.ready_queue = Queue()
        self.threads = set()
        self.thread_index = 1
        self._create_threads()

    def _create_workers(self):
        """Create initial threads."""
        for _ in range(self.max_threads):
            self._create_thread(self.thread_index)
            self.thread_index += 1

    def _create_worker(self, index):
        name = "ExecutorThread-{}".format(index)
        thread = ExecutorWorkerThread(self, name)
        self.threads.add(thread)

    def _start_workers(self):
        for thread in self.threads:
            thread.start()

    def execute(self, archive, context, root_node):
        executor_context = ExecutorJob(archive, context, root_node)
        self.process_queue.put(executor_context)


class ExecutorWorkerThread(Thread):

    def __init__(self, executor, name):
        super(ExecutorWorkerThread, self).__init__(name=name,
                                                   target=self.execute_loop,
                                                   args=(executor,))

    def execute_loop(self, executor):
        while 1:
            job = executor.queue.get()
            if job is None:
                break
