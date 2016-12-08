from ...command import SubCommand

from ...compat import text_type


class Check(SubCommand):
    help = "check the validity of a project"

    def add_arguments(self, parser):
        parser.add_argument("-l", "--location", dest="location", default=None, metavar="PATH",
                            help="location of the Moya server code")
        parser.add_argument("-i", "--ini", dest="settings", default=None, metavar="SETTINGSPATH",
                            help="path to project settings file")
        parser.add_argument("--server", dest="server", default="main", metavar="SERVERREF",
                            help="server element to use")

    def run(self):
        args = self.args
        from ...build import build_server
        try:
            build_result = build_server(self.location,
                                        self.get_settings(),
                                        server_element=args.server)
        except Exception as e:
            self.console.exception(e, tb=args.debug)
        else:
            if build_result:
                self.console("Server check ok", fg="green", bold=True).nl()
                self.console.xml(text_type(build_result.server))
            return 0
        return -1
