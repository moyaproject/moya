from __future__ import unicode_literals
from __future__ import print_function

from ...command import SubCommand
from ...context import Context
from ...console import Console, Cell
from ...compat import text_type
from ... import namespaces
from ... import build

from datetime import datetime
from collections import Counter
import sys


class TestRunner(object):

    def __init__(self, context, results):
        self.context = context
        self.results = results

    def __enter__(self):
        self.console = Console(text=True)
        self.context['.console'] = self.console

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def safe_to_string(obj):
    """Try to build a string representation of this object"""
    # Magic methods __unicode__ and __repr__ can (and often do) throw exceptions
    try:
        s = text_type(obj)
    except:
        try:
            s = repr(obj)
        except:
            s = "<failed to create string representation>"
    return s


class TestResults(object):
    def __init__(self, context, lib, suite):
        self.lib = lib
        self.context = context
        self.suite = suite
        self.setup_error = None
        self.teardown_error = None
        self.tests = []
        self.case = None
        self.output = []
        self.group = None

    def __repr__(self):
        return "<testresults>"

    def __moyaconsole__(self, console):
        self.summary(console)

    def clear_output(self):
        output = '\n'.join(self.output)
        del self.output[:]
        return output

    def get_output(self):
        text = self.context['.console'].get_text()
        self.context['.console'] = Console(text=True)
        return text

    def add_setup_error(self, element, error):
        self.setup_error = {'element': element,
                            'error': error,
                            'console_trace': self.get_output()}

    def add_teardown_error(self, element, error):
        self.teardown_error = {'element': element,
                               'error': error,
                               'console_trace': self.get_output()}

    def _test_result(self, status, **kwargs):
        result = {'status': status}
        result.update(kwargs)
        console_trace = self.get_output()
        result.update(case=self.case,
                      group=self.group,
                      console_trace=console_trace)
        self.tests.append(result)
        return result

    def add_error(self, element, error):
        console = Console(text=True, width=120)
        console.obj(self.context, error)
        trace = console.get_text()
        self._test_result('error',
                          element=element,
                          error=error,
                          trace=trace,
                          description=self.case.description,
                          msg=safe_to_string(error))

    def add_pass(self, element):
        self._test_result('pass',
                          element=element,
                          description=self.case.description)

    def add_fail(self, element, msg):
        self._test_result('fail',
                          element=element,
                          msg=msg,
                          description=self.case.description)

    def summary(self, console):
        passes, fails, errors = self.stats
        results = {}
        results['pass'] = passes
        results['fail'] = fails
        results['error'] = errors
        summary = "{fail} fail(s), {error} error(s), {pass} pass(es)".format(**results)
        if results['error'] or results['fail']:
            console.text(summary, fg="red", bold=True)
        else:
            console.text(summary, fg="green", bold=True)

    @property
    def stats(self):
        results = Counter(fail=0, error=0)
        results['pass'] = 0
        if self.setup_error is not None:
            results['error'] += 1
        if self.teardown_error is not None:
            results['error'] += 1
        for test in self.tests:
            results[test['status']] += 1
        return results['pass'], results['fail'], results['error']

    def report(self, console, show_trace=True, show_passes=False, verbose=False):

        def show_result(result, description, msg=None):
            if result == 'pass':
                fg = 'green'
            else:
                fg = 'red'
            console('[{}]\t'.format(result.upper()), fg=fg, bold=result != 'pass')(' {}'.format(description), dim=result == 'pass')
            if msg:
                console(' - {}'.format(msg), italic=True)
            console.nl()

        def show_output(test):
            if show_trace:
                trace = test['console_trace'].strip()
                if trace:
                    #console.div('begin captured output', dim=True)
                    #console(trace).nl().div('end captured output', dim=True)
                    console.table([[Cell(trace, fg='cyan', bold=True)]])
                    console.div()

        if verbose:
            console.div("[{}]".format(self.suite), fg="magenta", bold=True, italic=False)

        if self.setup_error is not None:
            console.error('setup failed, unable to run tests')
            console(self.setup_error['error'])
            show_output(self.setup_error)

        if self.teardown_error is not None:
            console.error('teardown failed')
            console(self.teardown_error['error'])
            show_output(self.teardown_error)

        for test in self.tests:
            status = test['status']
            if status == 'pass' and not show_passes:
                continue
            show_result(status, test['description'], test.get('msg', None))
            if status == 'error' and show_trace:
                console(test['error'])
            if status == 'fail' and show_trace:
                node = test['element']
                console.div('failed here', dim=True)
                #console.nl()
                console('File \"%s\"' % (node._location)).nl()
                console.xmlsnippet(node._code, node.source_line or 0, extralines=2 if verbose else 0)
            if status != 'pass':
                show_output(test)


class Test(SubCommand):
    """Run unit tests"""
    help = "unit tests"

    def add_arguments(self, parser):

        parser.add_argument(dest="location", default=None, nargs='+',
                            help="location of library (directory containing lib.ini) or a python import if preceded by 'py:', e.g. py:moya.libs.auth")
        parser.add_argument('--verbose', dest='verbose', action="store_true",
                            help="add extra information to reports")
        parser.add_argument('-o', '--output', dest="output", default=None, metavar="PATH",
                            help="write html report")
        #parser.add_argument('--break', dest="_break", default=False, action="store_true",
        #                    help="break on fail or error")
        parser.add_argument('--summary', dest="summary", default=False, action="store_true",
                            help="summarize all results")
        parser.add_argument('-a', '--automated', dest="automated", default=False, action="store_true",
                            help="disable breakpoints or anything that may block for user input")
        parser.add_argument('-q', '--quick', action="store_true", default=False,
                            help="run tests that aren't marked as 'slow'")
        parser.add_argument('--exclude', dest="exclude", default=None, nargs="+", metavar="GROUP",
                            help="exclude tests in a group or groups")
        parser.add_argument('--group', dest="group", default=None, nargs="+", metavar="GROUP",
                            help="run only tests in a group or groups")

    def run(self):
        args = self.args
        location = args.location

        console = self.console
        if args.output is not None:
            from moya.console import Console
            console = Console(html=True)

        def write_output():
            if args.output is not None:
                from moya import consolehtml
                html = console.get_text()
                html = consolehtml.render_console_html(html)
                with open(args.output, 'wb') as f:
                    f.write(html.encode('utf-8'))

        test_libs = []
        for location in args.location:
            archive, lib = build.build_lib(location, tests=True)
            lib_name = lib.long_name

            if archive.failed_documents:
                sys.stderr.write('library build failed\n')
                build.render_failed_documents(archive, console)
                write_output()
                return -1

            test_libs.append(lib)

        for lib_name in test_libs:
            if not lib.load_tests():
                sys.stderr.write('no tests for {}\n'.format(lib))
                return -1

        archive.finalize()

        if archive.failed_documents:
            sys.stderr.write('tests build failed\n')
            build.render_failed_documents(archive, console)
            write_output()
            return -1

        if args.automated:
            archive.suppress_breakpoints = True

        all_results = []

        for lib in test_libs:
            suites = list(lib.get_elements_by_type((namespaces.test, 'suite')))

            for suite_no, suite in enumerate(suites, 1):

                try:
                    suite_description = suite.description
                except:
                    suite_description = suite.libid

                if args.quick and suite.slow:
                    with self.console.progress("{} {} (skipped slow test)".format(lib, suite_description), 0):
                        pass
                    continue

                if args.exclude and suite.group is not None and suite.group in args.exclude:
                    with self.console.progress("{} {} (excluded group)".format(lib, suite_description), 0):
                        pass
                    continue

                if args.group and suite.group not in args.group:
                    with self.console.progress("{} {} (not in group)".format(lib, suite_description), 0):
                        pass
                    continue

                steps = 0
                setup = suite.get_child((namespaces.test, 'setup'))
                teardown = suite.get_child((namespaces.test, 'teardown'))
                if setup is not None:
                    setup_callable = archive.get_callable_from_element(setup)
                    steps += 1
                if teardown is not None:
                    teardown_callable = archive.get_callable_from_element(teardown)
                    steps += 1
                tests = list(suite.children((namespaces.test, 'case')))
                steps += len(tests)

                test_runner = {}
                context = Context({'_test_runner': test_runner})

                results = TestResults(context, lib, suite.description)
                results.group = suite._definition
                all_results.append(results)

                context['._test_results'] = results
                test_info = "({} of {})".format(suite_no, len(suites))
                progress_text = "{} {} {}".format(lib, suite_description, test_info)

                with self.console.progress(progress_text, steps) as progress:
                    if steps == 0:
                        progress.step()
                    else:
                        try:
                            with TestRunner(context, results):
                                if setup is not None:
                                    setup_callable(context)
                                    progress.step()
                        except Exception as e:
                            results.add_setup_error(setup, e)
                            progress.step('setup failed')
                        else:
                            with TestRunner(context, results):
                                for test in tests:
                                    results.case = test
                                    test_callable = archive.get_callable_from_element(test)
                                    try:
                                        test_return = test_callable(context)
                                    except Exception as e:
                                        results.add_error(test, e)
                                    else:
                                        if test_return != 'fail':
                                            results.add_pass(test)
                                    finally:
                                        progress.step()

                            try:
                                with TestRunner(context, results):
                                    if teardown is not None:
                                        teardown_callable(context)
                                        progress.step()
                            except Exception as e:
                                results.add_teardown_error(teardown, e)

        all_totals = {'pass': 0, 'fail': 0, 'error': 0}
        for result in all_results:
            _pass, fail, error = result.stats
            all_totals['pass'] += _pass
            all_totals['fail'] += fail
            all_totals['error'] += error
        summary = "{fail} fail(s), {error} error(s), {pass} pass(es)".format(**all_totals)

        if args.quick:
            console.div("Test results (quick) {}".format(datetime.now().ctime()))
        else:
            console.div("Test results {}".format(datetime.now().ctime()))
        test_count = sum(len(r.tests) for r in all_results)
        console.text('Ran {} test(s) in {} test suite(s) - {}'.format(test_count, len(all_results), summary))
        for results in all_results:
            results.report(console,
                           show_trace=not args.summary,
                           show_passes=args.verbose or args.summary,
                           verbose=args.verbose)

        header = ['lib', 'suite', 'passes', 'fails', 'errors']
        table = []
        passes = 0
        fails = 0
        errors = 0
        for result in all_results:
            _pass, fail, error = result.stats
            passes += _pass
            fails += fail
            errors += error
            _pass = Cell(_pass, fg="green" if _pass else 'white', bold=True)
            fail = Cell(fail, fg="red" if fail else "green", bold=True)
            error = Cell(error, fg="red" if error else "green", bold=True)
            table.append([result.lib.long_name, result.suite, _pass, fail, error])

        if not args.summary or args.verbose:
            console.nl()
            console.table(table, header_row=header)

        summary = "{fails} fail(s), {errors} error(s), {passes} pass(es)".format(fails=fails, errors=errors, passes=passes)
        if errors or fails:
            console.text(summary, fg="red", bold=True)
        else:
            console.text(summary, fg="green", bold=True)

        write_output()

        return fails
