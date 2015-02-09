from ...command import SubCommand
from ...wsgi import WSGIApplication
from ...compat import text_type, raw_input

try:
    import readline
except ImportError:
    pass


class Email(SubCommand):
    """Manage email"""
    help = "manage email"

    def add_arguments(self, parser):
        def add_common(parser):
            parser.add_argument("-l", "--location", dest="location", default=None, metavar="PATH",
                                help="location of the Moya server code")
            parser.add_argument("-i", "--ini", dest="settings", default=None, metavar="SETTINGSPATH",
                                help="Relative path to settings file")

        subparsers = parser.add_subparsers(title="email sub-commands",
                                           dest="email_subcommand",
                                           help="sub-command help")
        add_common(subparsers.add_parser("list",
                                         help="list smtp servers",
                                         description="display a list of smtp servers in the project"))
        add_common(subparsers.add_parser("check",
                                         help="check smtp servers",
                                         description="list smtp servers and check connectivity"))
        add_common(subparsers.add_parser("send",
                                         help="send an email",
                                         description="Send an email (useful for debugging)"))

        return parser

    def run(self):
        getattr(self, "sub_" + self.args.email_subcommand)()

    def sub_list(self):
        application = WSGIApplication(self.location, self.get_settings())
        archive = application.archive

        from ...console import Cell
        table = [(Cell("name", bold=True),
                  Cell("default?", bold=True),
                  Cell("host", bold=True),
                  Cell("port", bold=True),
                  Cell("username", bold=True),
                  Cell("password", bold=True))]
        for k, server in sorted(archive.mail_servers.items()):
            table.append([k, 'yes' if server.default else 'no', server.host, server.port, server.username or '', server.password or ''])
        self.console.table(table)

    def sub_check(self):
        application = WSGIApplication(self.location, self.get_settings())
        archive = application.archive

        from ...console import Cell
        table = [(Cell("name", bold=True),
                  Cell("host", bold=True),
                  Cell("port", bold=True),
                  Cell("status", bold=True))]
        for k, server in sorted(archive.mail_servers.items()):
            try:
                server.check()
            except Exception as e:
                status = Cell(text_type(e), bold=True, fg="red")
            else:
                status = Cell("OK", bold=True, fg="green")
            table.append([k, server.host, server.port, status])
        self.console.table(table)

    def sub_send(self):
        application = WSGIApplication(self.location, self.get_settings())
        archive = application.archive

        servers = ", ".join(archive.mail_servers.keys())

        server_name = raw_input("Which server? ({}) ".format(servers))
        if not server_name:
            server_name = archive.mail_servers.keys()[0]

        to = raw_input("To email: ")
        _from = raw_input("From email: ")
        subject = raw_input("Subject: ")
        body = raw_input("Body: ")

        from moya.mail import Email
        email = Email()
        email.set_from(_from)
        email.add_to(to)
        email.subject = subject
        email.text = body

        server = archive.mail_servers[server_name]
        self.console.div()
        self.console.text("Sending mail with server {}".format(server), fg="black", bold=True)
        server.send(email, fail_silently=False)
        self.console.text("Email was sent successfully", fg="green", bold=True)
