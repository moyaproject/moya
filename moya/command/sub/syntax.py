from __future__ import unicode_literals
from __future__ import print_function

from ...command import SubCommand

import sys
import io


class Syntax(SubCommand):
    """
    A tool to syntax highlight a file.

    Moya uses this in the debug library to syntax highlight files and errors.

    The syntax highlighter is somewhat naive. There maybe better general purpose syntax highlighters out there...

    """
    help = """syntax highlight a file"""

    def add_arguments(self, parser):
        parser.add_argument(dest='path', metavar="PATH",
                            help="Path to a file to highlight")
        parser.add_argument('-f', '--format', metavar="format", default='text',
                            help="format to highlight")
        parser.add_argument('-l', '--lines', dest="lines", action="store_true", default=False,
                            help="render lines numbers")
        return parser

    def run(self):
        args = self.args
        from moya import syntax
        with io.open(args.path, 'rt') as f:
            code = f.read()
        html = syntax.highlight(args.format, code, line_numbers=args.lines)
        sys.stdout.write(html + '\n')
