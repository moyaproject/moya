from __future__ import unicode_literals

from ...command import SubCommand
from ...wsgi import WSGIApplication
from ...compat import text_type


class Show(SubCommand):
    """Show an element's location and code"""
    help = "show an element"


    def add_arguments(self, parser):
        parser.add_argument(dest="elementref", metavar="ELEMENTREF",
                            help="an element reference to look up")
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

        try:
            app, element = archive.get_element(args.elementref)
        except Exception as e:
            self.error(text_type(e))
            return -1
        sibling = element.older_sibling
        start = element.source_line

        node = element
        while node:
            if node.older_sibling:
                node = node.older_sibling
                break
            node = node.parent
        end = node.source_line if node else None

        file_line = 'File "{}", line {}'.format(element._location, start)
        self.console(file_line).nl()
        self.console.snippet(element._code,
                                (start, end),
                                highlight_line=start,
                                line_numbers=True)