from __future__ import unicode_literals

from ...command import SubCommand
from ...wsgi import WSGIApplication
from ...console import Cell

from collections import defaultdict
from textwrap import dedent


class Preflight(SubCommand):
    """Run project preflight checks, return code is the total number of errors and fails"""
    help = "preflight checks"

    def add_arguments(self, parser):
        parser.add_argument("-a", "--app", dest="app", default=None, metavar="NAME")
        parser.add_argument("-l", "--location", dest="location", default=None, metavar="PATH",
                            help="location of the Moya server code")
        parser.add_argument("-i", "--ini", dest="settings", default=None, metavar="SETTINGSPATH",
                            help="path to projects settings file")
        parser.add_argument("--server", dest="server", default='main', metavar="SERVERREF",
                            help="server element to use")
        parser.add_argument("--hide", dest="hide", action="store_true",
                            help="hide passing checks")
        return parser

    def run(self):
        args = self.args
        application = WSGIApplication(self.location, self.get_settings(), args.server)

        preflight = application.preflight(report=False)

        table = []

        def style(check):
            if check:
                return {"fg": "red", "bold": True}
            else:
                return {"fg": "green"}
        all_totals = defaultdict(int)
        with self.console.progress('running preflight checks...', len(preflight)) as progress:
            for app, checks in progress(preflight):
                if args.hide and not checks:
                    continue
                totals = defaultdict(int)
                all_text = []
                for element, status, text in checks:
                    totals[status] += 1
                    all_totals[status] += 1
                    text = '\n'.join(l for l in dedent(text).splitlines() if l.strip())
                    all_text.append(text)

                errors = Cell(totals["error"], **style(totals["error"]))
                warnings = Cell(totals["warning"], **style(totals["warning"]))
                fails = Cell(totals["fail"], **style(totals["fail"]))
                table.append([app.name, warnings, errors, fails, "\n".join(all_text)])

        self.console.table(table, header_row=["app", "warnings", "errors", "fails", "info"])

        results = []
        for status in ("warning", "error", "fail"):
            results.append("{} {}(s)".format(all_totals[status], status))

        if sum(all_totals.values()):
            self.console.text(", ".join(results), fg="red", bold=True)
        else:
            self.console.text(", ".join(results), fg="green", bold=True)

        fatal = all_totals["error"] + all_totals["fail"]
        return fatal
