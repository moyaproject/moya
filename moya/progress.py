# -*- coding: utf-8 -*-
"""Simple text based progress bar"""


from __future__ import unicode_literals
from __future__ import division


from time import sleep


class Progress(object):
    """Renders a progress bar to the console"""
    def __init__(self, console, msg, num_steps=100, width=12, indent='', vanish=False):
        self.console = console
        self.msg = msg
        self.num_steps = num_steps
        self.max_line_size = 0
        self.complete = 0.0
        self._step = 0
        self.width = width
        self.indent = indent
        self.vanish = vanish

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
        self.render()

    def render(self, line_end='\r', color="magenta"):
        """Render a passable progress bar."""
        if not self.console.is_terminal():
            return

        start_char = '╺'
        mid_char = '━'
        end_char = '╸'

        bar = start_char + ((self.width - 2) * mid_char) + end_char

        num_bars = int(self.complete * self.width)
        completed = bar[:num_bars]
        remaining = bar[num_bars:]
        progress = "{}%".format(int(self.complete * 100.0)).ljust(4)
        size = len(self.indent) + len(progress) + 1 + len(completed) + len(remaining) + 1 + len(self.msg) + 1
        self.console('\r')(self.indent)(progress)(' ')(completed, color)(remaining, 'white')(' ' + self.msg)
        self.max_line_size = max(size, self.max_line_size)
        self.console((self.max_line_size - size) * ' ' + line_end).flush()

    def done(self, msg=None):
        if msg is not None:
            self.msg = msg
        if self.vanish:
            self.render()
            sleep(0.1)
            self.console(len(self.msg) * ' ')('\r')
        else:
            if not self.console.is_terminal():
                self.console.text(self.msg)
            else:
                self.render(line_end='\n')


class ProgressContext(object):
    """Progress context manager."""

    def __init__(self, progress):
        self.progress = progress

    def __enter__(self):
        """Hide cursor and render."""
        self.progress.console.show_cursor(False)
        self.progress.render()
        return self.progress

    def __exit__(self, *args, **kwargs):
        """Show 100% resume cursor."""
        self.progress.done()
        self.progress.console.show_cursor(True)


if __name__ == "__main__":
    from moya.console import Console
    from random import randint

    c = Console()
    p = Progress(c, "Extracting...", 100, width=24)

    with ProgressContext(p):
        for step in xrange(100):
            sleep(.03)
            p.step(msg = "Extracting... " + "*" * randint(5, 30) + '|')
