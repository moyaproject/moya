from __future__ import unicode_literals

import gettext

import logging
log = logging.getLogger('moya.startup')


class Translations(object):
    def __init__(self):
        self._translations = {}
        self._null = gettext.NullTranslations()

    def read(self, domain, localedir, languages):
        for lang in languages:
            try:
                translations = gettext.translation(domain,
                                                   localedir,
                                                   [lang])
            except IOError:
                log.warning("no translations found for language code '{}'".format(lang))
                translations = None

            if translations is not None:
                self._translations[lang] = translations

    def get(self, languages):
        for lang in languages:
            if lang in self._translations:
                return self._translations[lang]
        return self._null
