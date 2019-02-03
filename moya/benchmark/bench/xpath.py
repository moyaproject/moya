# -*- coding: utf-8 -*-
#
# Copyright (C) 2006-2008 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://genshi.edgewall.org/wiki/License.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://genshi.edgewall.org/log/.


from __future__ import print_function


try:
    from os import times

    def time_func():
        tup = times()
        # just user time
        return tup[0]  # + tup[1]


except ImportError:
    from time import time as time_func

from genshi.core import START, END
from genshi.path import Path
from genshi.input import XML


def benchmark(f, acurate_time=1):
    """Checks how much time does function f work. It runs it as
    many times as needed for avoiding inaccuracy"""

    runs = 1
    while True:
        start_time = time_func()
        for _ in xrange(runs):
            f()
        dt = time_func() - start_time
        if dt >= acurate_time:
            break
        runs *= 2
    return dt / runs


def spell(t):
    """Returns spelled representation of time"""
    units = [
        (0.000001, "microsecond", "microseconds"),
        (0.001, "milisecond", "miliseconds"),
        (1, "second", "seconds"),
        (60, "minute", "minutes"),
        (60 * 60, "hour", "hours"),
    ]
    i = 0
    at = abs(t)
    while i + 1 < len(units) and at >= units[i + 1][0]:
        i += 1
    t /= units[i][0]
    if t >= 2:
        name = units[i][2]
    else:
        name = units[i][1]
    return "%f %s" % (t, name)


def test_paths_in_streams(exprs, streams, test_strategies=False):
    for expr in exprs:
        print("Testing path %r" % expr)
        for stream, sname in streams:
            print('\tRunning on "%s" example:' % sname)

            path = Path(expr)

            def f():
                for e in path.select(stream):
                    pass

            t = spell(benchmark(f))
            print("\t\tselect:\t\t%s" % t)

            def f():
                path = Path(expr)
                for e in path.select(stream):
                    pass

            t = spell(benchmark(f))
            print("\t\tinit + select:\t%s" % t)

            if test_strategies and len(path.paths) == 1:
                from genshi.path import (
                    GenericStrategy,
                    SingleStepStrategy,
                    SimplePathStrategy,
                )
                from genshi.tests.path import FakePath

                strategies = (GenericStrategy, SingleStepStrategy, SimplePathStrategy)
                for strategy in strategies:
                    if not strategy.supports(path.paths[0]):
                        continue
                    print("\t\t%s Strategy" % strategy.__name__)
                    fp = FakePath(strategy(path.paths[0]))

                    def f():
                        for e in fp.select(stream):
                            pass

                    t = spell(benchmark(f))
                    print("\t\t\tselect:\t\t%s" % t)


def test_documents(test_strategies=False):
    streams = []

    s = XML(
        """\
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="pl" xmlns:py="http://genshi.edgewall.org/" py:strip="" lang="en">
    <head>
        <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
        <title>Foo</title>
    </head>
    <body>
        <h1>Hello</h1>
    </body>
</html>
"""
    )
    streams.append((s, "small document"))

    s = XML(
        """\
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="pl" xmlns:py="http://genshi.edgewall.org/" py:strip="" lang="en">
    <head>
        <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
        <title>Foo</title>
    </head>
    <body>
        <h1>Hello</h1>
        <div id="splash">
            <ul>
                <li><a class="b1" href="http://genshi.edgewall.org/">
                        <strong>Genshi</strong>
                        Python toolkit for generating output for the web</a></li>
                <li><a class="b2" href="http://babel.edgewall.org/">
                        <strong>Babel</strong>
                        Python library for I18n/L10n in web applications</a></li>
                <li><a class="b3" href="http://bitten.edgewall.org/">
                        <strong>Bitten</strong>
                        Continuous integration plugin for Trac</a></li>
                <li><a class="b4" href="http://posterity.edgewall.org/">
                        <strong>Posterity</strong>
                        Web-based email system</a></li>
            </ul>
            <div id="trac-splash">
                <a href="http://trac.edgewall.org/">
                    <strong>Trac</strong> Web-based lightweight project management
                    system
                </a>
            </div>
        </div>
    </body>
</html>
"""
    )
    streams.append((s, "big document"))

    paths = [
        ".",
        "*|text()",
        "html",
        'html[@lang="en"]',
        "html/body/h1/text()",
        "html/body/div/a/@href",
        'html/body/div[@id="splash"]/a[@class="b4"]/strong/text()',
        "descendant-or-self::text()",
        "descendant-or-self::h1/text()",
    ]
    test_paths_in_streams(paths, streams, test_strategies)


if __name__ == "__main__":
    from sys import argv

    if "--strategies" in argv:
        test_strategies = True
    else:
        test_strategies = False
    test_documents(test_strategies)
