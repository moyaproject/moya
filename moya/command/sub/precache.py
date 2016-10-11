from __future__ import unicode_literals
from __future__ import print_function

from fs.walk import walk_files

from ...command import SubCommand
from ...wsgi import WSGIApplication
from ...compat import text_type
from ...context.expression import Expression


class PreCache(SubCommand):
    """Load resources in to cache in advance"""
    help = "pre-cache resources to speed up initial requests "

    def add_arguments(self, parser):
        parser.add_argument("-l", "--location", dest="location", default=None, metavar="PATH",
                            help="location of the Moya server code")
        parser.add_argument("-i", "--ini", dest="settings", default=None, metavar="SETTINGSPATH",
                            help="path to projects settings file")

    def run(self):
        console = self.console

        console.text("loading project", bold=True)
        application = WSGIApplication(self.location,
                                      self.get_settings(),
                                      disable_autoreload=True,
                                      master_settings=self.master_settings)
        archive = application.archive

        try:
            templates_fs = archive.get_filesystem('templates')
        except KeyError:
            self.error("templates filesystem not found")
        else:
            template_engine = archive.get_template_engine()
            paths = list(walk_files(templates_fs, wildcards=['*.html']))

            console.text('pre-caching templates', bold=True)

            failed_templates = []
            with console.progress('pre-caching templates', width=20) as progress:
                progress.set_num_steps(len(paths))
                for path in paths:
                    progress.step(msg=path)
                    try:
                        template_engine.env.get_template(path)
                    except Exception as e:
                        failed_templates.append((path, text_type(e)))

        if archive.has_cache('parser'):
            parser_cache = archive.get_cache('parser')

            console.text('pre-caching expressions', bold=True)

            elements = []
            for lib in archive.libs.values():
                for _type, _elements in lib.elements_by_type.items():
                    elements.extend(_elements)

            with console.progress('caching expressions', width=20) as progress:
                progress.set_num_steps(len(elements))
                for el in elements:
                    progress.step(msg=getattr(el, 'libid', ''))
                    el.compile_expressions()

            Expression.dump(parser_cache)
        else:
            console.error("no 'parser' cache available to store expressions")

        console.text('done', fg="green", bold=True)
