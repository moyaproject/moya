from __future__ import unicode_literals

from ...command import SubCommand
from ...wsgi import WSGIApplication
from ...compat import text_type
from ... import pilot


class Call(SubCommand):
    """Call moya code in project context"""
    help = "call moya code in project context"

    def add_arguments(self, parser):
        parser.add_argument(dest="elementref", metavar="ELEMENTREF",
                            help="element to call")
        parser.add_argument(dest="params", metavar="PARAMETER", nargs='*',
                            help="parameter(s) for call, e.g. moya call app#macro 3.14 foo=bar")
        parser.add_argument("-l", "--location", dest="location", default=None, metavar="PATH",
                            help="location of the Moya server code")
        parser.add_argument("-i", "--ini", dest="settings", default=None, metavar="SETTINGSPATH",
                            help="path to project settings file")
        return parser

    def run(self):
        args = self.args
        application = WSGIApplication(self.location,
                                      self.get_settings(),
                                      disable_autoreload=True)
        archive = application.archive
        context = application.get_context()
        application.populate_context(context)
        pilot.context = context

        def make_param(v):
            if v == "True":
                return True
            elif v == "False":
                return False
            elif v == "None":
                return None
            if v.isdigit():
                return int(v)
            try:
                return float(v)
            except ValueError:
                pass
            return v

        positional_args = []
        keyword_args = {}
        for param in args.params:
            if '=' in param:
                k, v = param.split('=', 1)
                k = k.strip()
                v = v.strip()
                keyword_args[k] = make_param(v)
            else:
                positional_args.append(make_param(param))

        ret = archive.call(args.elementref,
                           context,
                           None,
                           *positional_args,
                           **keyword_args)

        application.finalize(context)

        if ret is not None:
            self.console(text_type(ret)).nl()
