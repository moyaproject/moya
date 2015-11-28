from ...command import SubCommand
from ...wsgi import WSGIApplication
from ... import db


class DB(SubCommand):
    """Manage project databases"""
    help = "manage project database(s)"

    def add_arguments(self, parser):

        subparsers = parser.add_subparsers(title="db sub-commands",
                                           dest="dbsubcommand",
                                           help="database action")

        def add_common(parser):
            parser.add_argument("-l", "--location", dest="location", default=None, metavar="PATH",
                                help="location of the Moya server code")
            parser.add_argument("-i", "--ini", dest="settings", default=None, metavar="SETTINGSPATH",
                                help="Relative path to settings file")

        parser = subparsers.add_parser("sync",
                                       help="sync database(s)",
                                       description="create tables from models")
        add_common(parser)

        parser = subparsers.add_parser("list",
                                       help="list databases",
                                       description="display databases used in project")
        add_common(parser)

        parser = subparsers.add_parser("validate",
                                       help="validated models",
                                       description="detect any problems in your database models")
        add_common(parser)

        return parser

    def run(self):
        getattr(self, "sub_" + self.args.dbsubcommand)()

    def sub_sync(self):
        application = WSGIApplication(self.location,
                                      self.get_settings(),
                                      validate_db=True,
                                      disable_autoreload=True,
                                      master_settings=self.master_settings)
        archive = application.archive
        return db.sync_all(archive, self.console)

    def sub_list(self):
        application = WSGIApplication(self.location,
                                      self.get_settings(),
                                      validate_db=False,
                                      disable_autoreload=True,
                                      master_settings=self.master_settings)
        archive = application.archive
        engines = archive.database_engines
        from ...console import Cell
        table = [(Cell("Name", bold=True), Cell("DB", bold=True))]
        table += sorted([(name, engine.engine_name) for name, engine in engines.items()],
                        key=lambda d: d[0])
        self.console.table(table)

    def sub_validate(self):
        from ...build import build_server
        build_result = build_server(self.location,
                                    self.get_settings())

        fails = db.validate_all(build_result.archive, self.console)
        if fails:
            self.console.error("{} model(s) failed to validate".format(fails))
        else:
            self.console.text("models validated successfully", fg="green", bold=True)
        return fails
