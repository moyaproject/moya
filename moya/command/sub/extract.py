from __future__ import unicode_literals
from __future__ import print_function

from ...command import SubCommand
from ...wsgi import WSGIApplication
from ...console import Cell
from ...template.moyatemplates import Template

from datetime import datetime

from fs.path import join
import os.path
from collections import defaultdict

import polib
import pytz


class Extract(SubCommand):
    """Extract translatable text from libraries"""
    help = "extract translatable text"

    def add_arguments(self, parser):
        parser.add_argument(dest="libs", default=None, metavar="LIB NAME", nargs='+',
                            help="Extract text from these libs")
        parser.add_argument("-l", "--location", dest="location", default=None, metavar="PATH",
                            help="location of the Moya server code")
        parser.add_argument("-i", "--ini", dest="settings", default=None, metavar="SETTINGSPATH",
                            help="path to projects settings file")
        parser.add_argument("-m", "--merge", dest="merge", action="store_true",
                            help="merge translatable strings with existing .pot file")
        parser.add_argument('-o', '--overwrite', dest="overwrite", action="store_true",
                            help="overwrite existing .pot file")

    def run(self):
        args = self.args
        application = WSGIApplication(self.location,
                                      self.get_settings(),
                                      disable_autoreload=True,
                                      master_settings=self.master_settings)
        archive = application.archive

        try:
            libs = [archive.libs[lib_name] for lib_name in args.libs]
        except KeyError:
            self.console.error('No lib with name "{}" installed'.format(lib_name))
            return -1

        table = []

        for lib in libs:

            template_text = set()
            extract_text = defaultdict(lambda: {"occurrences": []})

            if not lib.translations_location:
                table.append([lib.long_name,
                              Cell("translations not enabled", fg="red", bold=True),
                              ''])
                continue

            filename = "{}.pot".format(lib.long_name.replace('.', '_'))
            translations_dir = lib.load_fs.getsyspath(lib.translations_location)

            def add_text(path, line, text, comment=None, plural=None, attr=None, context=None):
                rel_path = os.path.relpath(path, translations_dir)
                entry = extract_text[(text, plural, attr, context)]
                if attr is not None and context is not None:
                    context = "attribute '{}'".format(attr)
                if plural is not None:
                    entry['msgid'] = text
                    entry['msgid_plural'] = plural
                    entry['msgstr_plural'] = {'0': '', '1': ''}
                else:
                    entry['msgid'] = text
                if context is not None:
                    entry['msgctxt'] = context

                entry['occurrences'].append((rel_path, line))
                if comment is not None:
                    entry['comment'] = comment

            with self.console.progress("extracting {}".format(lib), len(lib.documents)) as progress:
                for doc in lib.documents:
                    progress.step()
                    for element in doc.elements.itervalues():
                        if element._translate_text:
                            text = element._text.strip()
                            if text:
                                add_text(element._location,
                                         element.source_line,
                                         text,
                                         comment=unicode(element))
                        for name, attribute in element._tag_attributes.items():
                            if attribute.translate or name in element._translatable_attrs:
                                text = element._attrs.get(name, '').strip()
                                if text:
                                    add_text(element._location,
                                             element.source_line,
                                             text,
                                             attr=name,
                                             comment="attribute '{}' of {}".format(name, unicode(element)))
                    if 'location' in lib.templates_info:
                        engine = archive.get_template_engine('moya')
                        with lib.load_fs.opendir(lib.templates_info['location']) as templates_fs:
                            for path in templates_fs.walkfiles():
                                sys_path = templates_fs.getsyspath(path, allow_none=True) or path
                                contents = templates_fs.getbytes(path)
                                template = Template(contents, path)
                                template.parse(engine.env)

                                for trans_text in template.translatable_text:
                                    line, start, end = trans_text.location
                                    text = trans_text.text
                                    comment = trans_text.comment
                                    plural = trans_text.plural

                                    translatable_text = (path, line, start, text, plural)
                                    if translatable_text not in template_text:
                                        add_text(sys_path, line, text, comment, plural=plural, context=trans_text.context)
                                        template_text.add(translatable_text)

            now = pytz.UTC.localize(datetime.utcnow())
            po = polib.POFile()

            for text in extract_text.values():
                po.append(polib.POEntry(**text))

            po.metadata = {
                'POT-Creation-Date': now.strftime('%Y-%m-%d %H:%M%z'),
                'Project-Id-Version': lib.version,
                'Language': lib.default_language or 'en',
                'MIME-Version': '1.0',
                'Content-Type': 'text/plain; charset=utf-8',
                'Content-Transfer-Encoding': '8Bit',
                'Plural-Forms': 'nplurals=2; plural=(n != 1);'
            }

            if lib.translations_location:

                lib.load_fs.makedir(lib.translations_location, recreate=True)

                translations_location = lib.load_fs.getsyspath(lib.translations_location)
                translation_path = os.path.join(translations_location, filename)

                if os.path.exists(translation_path) and not args.overwrite:
                    if not args.merge:
                        self.console.error('message file "{}" exists, see --merge or --overwrite options'.format(filename))
                        return -1
                    existing_po = polib.pofile(translation_path)
                    po.merge(existing_po)
                    po.save(translation_path)
                else:
                    po.save(translation_path)

                locale_fs = lib.load_fs.opendir(lib.translations_location)

                for lang in lib.languages:
                    locale_fs.makedirs("{}/LC_MESSAGES/".format(lang), recreate=True)

                table.append([lib.long_name,
                              Cell(join(lib.translations_location, filename), fg="green", bold=True),
                              Cell(len(po), bold=True)])

        self.console.table(table, header_row=["lib", "file", "no. strings"])
