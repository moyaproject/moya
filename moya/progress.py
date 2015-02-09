from __future__ import unicode_literals
from __future__ import division

"""Simple text based progress bar"""


class Progress(object):
    """Renders a progress bar to the console"""
    def __init__(self, console, msg, num_steps=100, width=12, indent=''):
        self.console = console
        self.msg = msg
        self.num_steps = num_steps
        self.max_line_size = 0
        self.complete = 0.0
        self._step = 0
        self.width = width
        self.indent = indent

    def set_num_steps(self, num_steps):
        self.num_steps = num_steps

    def step(self, count=1, msg=None):
        self.update(self._step + count, msg)

    def __call__(self, iterable):
        for item in iterable:
            yield item
            self.step()

    def update(self, step, msg=None):
        if step is not None:
            self._step = step
        if self.num_steps is None:
            complete = 0.0
        elif not self.num_steps:
            complete = 1.0
        else:
            complete = float(self._step) / self.num_steps
        self.complete = min(complete, 1.0)
        if msg is not None:
            self.msg = msg
        if not self.console.is_terminal():
            return
        self.render()
        # if self.step == self.num_steps:
        #     self.done()
        # else:
        #     self.render()

    def render(self, line_end='\r'):
        progress = "{}%".format(int(self.complete * 100.0)).ljust(4)
        num_bars = int(self.complete * self.width)
        bars = '=' * num_bars
        bars = bars.ljust(self.width, ' ')
        out = "{indent}[{bars}] {progress}".format(indent=self.indent,
                                                   bars=bars,
                                                   progress=progress)

        if self.msg:
            out = "\r{1} {0}".format(self.msg, out)

        out = out.expandtabs()

        self.max_line_size = max(len(out), self.max_line_size)
        out = out.ljust(self.max_line_size + 1, ' ') + line_end

        self.console(out).flush()

    def done(self, msg=None):
        if msg is not None:
            self.msg = msg
        self.render(line_end='\n')


class ProgressContext(object):
    def __init__(self, progress):
        self.progress = progress

    def __enter__(self):
        self.progress.console.show_cursor(False)
        self.progress.render()
        return self.progress

    def __exit__(self, *args, **kwargs):
        self.progress.done()
        self.progress.console.show_cursor(True)


if __name__ == "__main__":
    from time import sleep
    from moya.console import Console
    c = Console()
    p = Progress(c, "Extracting...", 100)
    p.render()

    for step in xrange(100):
        sleep(.01)
        p.step()
    p.render()
    print