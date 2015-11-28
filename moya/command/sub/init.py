from __future__ import print_function
from __future__ import unicode_literals
from __future__ import absolute_import

from ...command import SubCommand
from ...console import Cell
from ...wsgi import WSGIApplication
from ... import namespaces
from ... import db

try:
    import readline
except ImportError:
    pass


class Init(SubCommand):
    """initialize a site for first use"""
    help = """initialize a site for first use"""

    def add_arguments(self, parser):
        parser.add_argument("-l", "--location", dest="location", default=None, metavar="PATH",
                            help="location of the Moya server code")
        parser.add_argument("-i", "--ini", dest="settings", default=None, metavar="SETTINGSPATH",
                            help="path to project settings")

    def run(self):
        args = self.args
        console = self.console
        console.text("Initializing site...", bold=True)

        application = WSGIApplication(self.location,
                                      self.get_settings(),
                                      validate_db=True,
                                      disable_autoreload=True,
                                      master_settings=self.master_settings)
        archive = application.archive
        db.sync_all(archive, self.console, summary=False)

        commands = [command for command in archive.get_elements_by_type(namespaces.default, 'command')
                    if command._init]

        commands.sort(key=lambda c: c._priority, reverse=True)

        fail = None
        for command in commands:
            if fail:
                break
            for app_name in archive.apps_by_lib[command.lib.long_name]:
                app = archive.apps[app_name]
                app_id = command.get_appid(app=app)

                console.table([["running 'moya {}'".format(app_id), command._synopsis]])
                result = self.moya_command.project_invoke(app_id,
                                                          application=application,
                                                          root_vars={'init': True})
                if result != 0:
                    fail = result
                    break

        if not fail:
            msg = '''Site is ready for use!\nRun "moya runserver" from the project directory.'''
            console.table([[Cell(msg, fg="green", bold=True)]])
        else:
            msg = '''A command failed to complete -- check above for any error messages.'''
            console.table([[Cell(msg, fg="red", bold=True)]])
