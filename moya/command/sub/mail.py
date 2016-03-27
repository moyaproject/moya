from ...command import SubCommand
from ...wsgi import WSGIApplication
from ...compat import text_type, raw_input, urlparse

import sys
import json

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
                                help="relative path to settings file")

        subparsers = parser.add_subparsers(title="email sub-commands",
                                           dest="email_subcommand",
                                           help="sub-command help")
        add_common(subparsers.add_parser("list",
                                         help="list smtp servers",
                                         description="display a list of smtp servers in the project"))
        add_common(subparsers.add_parser("check",
                                         help="check smtp servers",
                                         description="list smtp servers and check connectivity"))
        add_common(subparsers.add_parser("test",
                                         help="send a test email",
                                         description="send a test email (useful for debugging)"))
        render_parser = subparsers.add_parser("render",
                                              help="render an email",
                                              description="render and email to the console")
        add_common(render_parser)
        render_parser.add_argument(dest="emailelement", metavar="ELEMENTREF",
                                   help="email element to render")
        render_parser.add_argument('--text', dest="text", action="store_true",
                                   help='render email text')
        render_parser.add_argument('--html', dest="html", action="store_true",
                                   help='render email html')
        render_parser.add_argument('-b', '--open-in-browser', dest="open", action="store_true",
                                   help="open the email in the browser")
        render_parser.add_argument('--let', dest='params', nargs="*",
                                   help="parameters in the form foo=bar")
        render_parser.add_argument('--data', dest='datafile', default=None,
                                   help="path to JSON file containing email template data")
        render_parser.add_argument('--url', dest='url', default="http://127.0.0.1:8000",
                                   help="emulate email sent from this URL")

        return parser

    def run(self):
        getattr(self, "sub_" + self.args.email_subcommand)()

    def sub_list(self):
        application = WSGIApplication(self.location,
                                      self.get_settings(),
                                      disable_autoreload=True,
                                      master_settings=self.master_settings)
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

    def sub_test(self):
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

    def sub_render(self):
        application = WSGIApplication(self.location, self.get_settings(), disable_autoreload=True)
        archive = application.archive

        args = self.args

        try:
            app, element = archive.get_element(args.emailelement)
        except Exception as e:
            self.error(text_type(e))
            return -1

        params = {}
        if args.params:
            for p in args.params:
                if '=' not in p:
                    sys.stderr.write("{} is not in the form <name>=<expression>\n".format(p))
                    return -1
                k, v = p.split('=', 1)
                params[k] = v

        if args.datafile:
            try:
                with open(args.datafile, 'rb') as f:
                    td_json = f.read()
            except IOError as e:
                self.error(e)
                return -1

            td = json.loads(td_json)
            params.update(td)

        from moya.mail import Email
        from moya.context import Context

        email = Email(data=params)
        email.app = app
        email.subject = "Render Email"
        email.email_element = element

        url_parsed = urlparse(args.url)
        host = "{}://{}".format(url_parsed.scheme, url_parsed.netloc)

        context = Context()
        archive.populate_context(context)
        context['.app'] = app
        from moya.request import MoyaRequest
        request = MoyaRequest.blank(args.url)
        application.server._populate_context(archive, context, request)
        application.server.set_site(archive, context, request)

        context.root['settings'] = archive.settings

        email_callable = archive.get_callable_from_element(element, app=app)
        try:
            email_callable(context, app=email.app, email=email)
        except Exception as e:
            if hasattr(e, '__moyaconsole__'):
                e.__moyaconsole__(self.console)
                return -1
            raise

        if not args.html and not args.text:
            table = []
            table.append(['text', email.text])
            table.append(['html', email.html])
            self.console.table(table)
        elif args.text:
            self.console(email.text)
        else:
            self.console(email.html)

        if args.open:
            import webbrowser
            import tempfile
            path = tempfile.mktemp(prefix='moyaemail', suffix=".html")
            with open(path, 'wt') as f:
                f.write(email.html)
            webbrowser.open('file://{}'.format(path))
