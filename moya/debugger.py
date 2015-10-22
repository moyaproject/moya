from __future__ import unicode_literals
from __future__ import absolute_import

import sys
from cmd import Cmd
try:
    import readline
    readline  # hides a warning
except ImportError:
    pass

from .console import Cell
from .elements.help import help
from . import namespaces
from .tools import extract_namespace
from .compat import text_type


def winpdb():
    import rpdb2
    rpdb2.start_embedded_debugger("password")


# Global containing last command, None will show help
_previous_command = None


class MoyaCmdDebugger(Cmd):
    prompt = "moya>"

    command_help = [
        (
            ' let foo="bar"',
            """
            Set foo to \"bar\" in the context.
            """
        ),
        (
            ' foo',
            """
            Evaulate the 'foo' in the current context and display the result. Any valid expression will also work, for example 1 + 1, "Hello," + "World!" etc.
            """
        ),
        (
            ' foo?',
            """
            Convert the value of 'foo' to text.

            """
        ),
        (
            ' foo??',
            """
            Convert the value of 'foo' to a Moya expression (if possible).

            """
        ),
        (
            ' foo???',
            """
            Covert the value of 'foo' to the internal (Python) representation.
            """
        ),
        (
            ' $$',
            """
            Show the current scope
            """
        ),
        (
            't, stack [EXTRALINES]',
            """
            Show the current call stack. If EXTRALINES is provided, it should be an integer indicating the number of lines of code to show in the stack trace.
            """
        ),
        (
            "s, step",
            """
            Advance to next logic element.
            """
        ),
        (
            "o, over",
            """
            Step over the next logic element.
            """
        ),
        (
            'u, out',
            """
            Step out of the current call.
            """
        ),
        (
            "c, continue",
            """
            Run until the next breakpoint, or to the end of the logic code.

            """
        ),
        (
            "help",
            """
            Show this help information.
            """
        ),
        (
            "help TAG",
            """
            Show help information for a given tag.
            """
        ),
        (
            "w, where [EXTRALINES]",
            """
            Show the current position in moya code, if EXTRALINES it provided, it should be an integer indicating the number of additional lines either side of the current position to display.
            """
        ),
        (
            "watch",
            """
            When followed by an expression, it will be added to the watch list (a table of expressions and their results). When given without an argument, the watch list will be reset.
            """
        ),
        (
            "winpdb PASSWORD",
            """
            Launch WinPDB to debug the next Python call.
            """
        ),
        (
            "ctrl+D",
            """
            Exit debugger and continue with moya code execution. Ignores all further breakpoints to the end of the request.

            """
        ),
        (
            "<ENTER>",
            """
            Repeat last command.
            """
        ),
        (
            "v, view",
            """
            Display the full view of the currently executing moya code.

            """
        ),
        (
            "e, eval",
            """
            Evaluates an expression, or shows the current frame if no argument is given.
            """
        ),
        (
            "exit",
            "Stop execution of Moya code and exit debugger."
        ),
        (
            "r, run",
            "Exit debugger and continue with moya code execution. Ignores all further breakpoints in the session."
        )
    ]

    def __init__(self, archive, console):
        self.console = console
        self.archive = archive
        Cmd.__init__(self)

    def default(self, line):
        if not isinstance(line, text_type):
            line = line.decode(sys.stdin.encoding)
        self.usercmd = line
        global _previous_command
        _previous_command = line

    def postcmd(self, stop, line):
        if stop is False:
            return False
        if _previous_command is None:
            return self.do_help()
        self.usercmd = _previous_command
        return True

    def do_help(self, line=''):
        if line:
            ns, tag = extract_namespace(line)
            self.console.div("Help on <%s/>" % tag, fg="blue", bold=True)
            help(self.archive, self.console, "{%s}%s" % (ns or namespaces.default, tag))
            return False

        self.console.div("Moya Debugger", fg="blue", bold=True)
        self.console.text("Moya's Debugger http://www.moyaproject.com/debugger/", fg="black", bold=True).nl()
        table = [(Cell("Command", bold=True), Cell("Description", bold=True))]
        command_help = sorted(self.command_help, key=lambda h: h[0])

        def format_desc(desc):
            lines = [l.strip() for l in desc.splitlines() if l.strip()]
            return "\n".join(lines)
        for i, (command, desc) in enumerate(command_help):
            table.append([Cell(command, bold=True, fg="green"),
                          Cell(format_desc(desc))])
        self.console.table(table, header=True)
        return False
