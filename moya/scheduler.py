from __future__ import unicode_literals
from __future__ import print_function

from threading import Thread, RLock, Event
from datetime import datetime, timedelta

from operator import attrgetter


import logging
log = logging.getLogger('moya.runtime')


class Task(object):
    """A task scheduled for a given time"""
    def __init__(self, name, callable, run_time=None, repeat=None):
        self.name = name
        self.callable = callable
        self.run_time = run_time
        self.repeat = repeat

    def __unicode__(self):
        if self.repeat:
            return "<task '{}' repeats {}>".format(self.name, self.repeat)
        else:
            return "<task '{}'>".format(self.name)

    __repr__ = __unicode__

    def advance(self):
        """Set run time to next cycle"""
        if self.repeat:
            self.run_time = self.run_time + self.repeat
            return True
        else:
            return False

    def ready(self, t):
        """Check if this task is ready to be execute"""
        return t >= self.run_time

    def run(self):
        """Run the task in it's own thread"""
        run_thread = Thread(target=self._run)
        run_thread.start()

    def _run(self):
        try:
            self.callable()
        except Exception as e:
            log.exception("Error in scheduled task '%s'", self.name)


class Scheduler(Thread):
    """A thread that manages scheduled / repeating tasks"""

    # The granularity at which tasks can be scheduled
    # Super precision is not required given that tasks are unlikely to be more than one a minute
    poll_seconds = 1

    def __init__(self):
        super(Scheduler, self).__init__()
        self.lock = RLock()
        self.quit_event = Event()
        self.tasks = []
        self.new_tasks = []

    def run(self):
        while 1:
            # Better than a sleep because we can interrupt it
            self.quit_event.wait(self.poll_seconds)
            if self.quit_event.is_set():
                break
            with self.lock:
                self.tasks += self.new_tasks
                del self.new_tasks[:]
            self._check_tasks()
        del self.tasks[:]
        with self.lock:
            del self.new_tasks[:]

    def stop(self, wait=True):
        """Stop processing tasks and block till everything has quit"""
        self.quit_event.set()
        if wait:
            self.join()

    def _check_tasks(self):
        if not self.tasks:
            return
        t = datetime.utcnow()
        ready_tasks = None
        self.tasks.sort(key=attrgetter('run_time'))
        for i, task in enumerate(self.tasks):
            if not task.ready(t):
                ready_tasks = self.tasks[:i]
                del self.tasks[:i]
                break
        else:
            ready_tasks = self.tasks[:]
            del self.tasks[:]

        if ready_tasks:
            for task in ready_tasks:
                if self.quit_event.is_set():
                    break
                task.run()
                if task.advance():
                    self.tasks.append(task)

    def add_repeat_task(self, name, callable, repeat):
        """Add a task to be invoked every `repeat` seconds"""
        if isinstance(repeat, (int, long, float)):
            repeat = timedelta(seconds=repeat)
        run_time = datetime.utcnow() + repeat
        task = Task(name, callable, run_time=run_time, repeat=repeat)
        with self.lock:
            self.new_tasks.append(task)
        return task


if __name__ == "__main__":
    import time
    def hello():
        print("Hello")
    def world():
        print("world")
    scheduler = Scheduler()
    print(scheduler.add_repeat_task("hello", hello, repeat=5))
    print(scheduler.add_repeat_task("world", world, repeat=3))
    scheduler.start()

    try:
        while 1:
            time.sleep(1)
    except:
        scheduler.stop()
        print("Stopped")
        raise
