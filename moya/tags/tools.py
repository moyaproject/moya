from __future__ import unicode_literals

from ..elements.elementbase import LogicElement, Attribute
from ..logic import DeferNodeContents

from time import time, clock

import logging
log = logging.getLogger('moya.runtime')


class Timer(LogicElement):
    """
    Time a block of code, and log the elapsed time. The log will display two time values; the first is the wall time, the second is [i]processor time[/i]. Processor time is more useful for profiling, as it doesn't include the time spent waiting on IO.

    """

    msg = Attribute("msg", default="elapsed")
    ms = Attribute("Display milliseconds", type="boolean", default=False)
    console = Attribute("Display to console?", type="boolean", default=False)

    class Help:
        synopsis = "time a block of code"
        help = """
        <timer msg="time slow macro">
            <call macro="#slow" />
        </timer>
        """

    def logic(self, context):
        to_console = self.console(context)
        msg = self.msg(context)
        ms = self.ms(context)
        start = time()
        start_clock = clock()
        try:
            yield DeferNodeContents(self)
        finally:
            taken_clock = clock() - start_clock
            taken = time() - start
            if ms:
                result = ("{}: clock {:.2f}ms; cpu {:.2f}ms".format(msg, taken * 1000, taken_clock * 1000))
            else:
                result = ("{}: clock {:.2f}s; cpu {:.2f}s".format(msg, taken, taken_clock))
            if to_console:
                context['.console'].text(result)
            else:
                log.debug(result)


class ProfilePython(LogicElement):
    """
    Profile Python code.

    """

    class Help:
        synopsis = "profile python code"

    _sort_choices = [
        'calls',  # call count
        'cumulative',  #  cumulative time
        'cumtime',  # cumulative time
        'file',  # file name
        'filename',  # file name
        'module',  #    file name
        'ncalls',  #    call count
        'pcalls',  #    primitive call count
        'line',  #  line number
        'name',  #  function name
        'nfl',  #   name/file/line
        'stdname',  #   standard name
        'time',  #  internal time
        'tottime'
    ]
    sort = Attribute("column to sort by", choices=_sort_choices, default="cumtime")
    max = Attribute("number of stats to display", type="integer", default=20)

    def logic(self, context):
        sort, max_stats = self.get_parameters(context, 'sort', 'max')
        import cProfile, pstats
        prof = cProfile.Profile()
        prof.enable()
        try:
            yield DeferNodeContents(self)
        finally:
            prof.disable()
            stats = pstats.Stats(prof)
            stats.sort_stats(sort)
            stats.print_stats(max_stats)
