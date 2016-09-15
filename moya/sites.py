from __future__ import unicode_literals
from __future__ import print_function

from .interface import AttributeExposer
from .compat import iteritems, implements_to_string, text_type
from .settings import SettingsContainer

from babel import Locale

import gettext
import locale
import re
from collections import namedtuple
import logging

log = logging.getLogger('moya.runtime')
startup_log = logging.getLogger('moya.startup')


SiteMatch = namedtuple("SiteMatch", ["site", "site_data", "custom_data"])


@implements_to_string
class LocaleProxy(AttributeExposer):

    __moya_exposed_attributes__ = ["language",
                                   "territory",
                                   "language_name",
                                   "display_name",
                                   "territory_name",
                                   "territories",
                                   "languages",
                                   "months"]

    def __init__(self, locale_name='en_US.UTF-8'):
        self._locale_name = locale_name
        self._locale = Locale.parse(locale_name)
        self._territories = dict(self._locale.territories)
        self._languages = dict(self._locale.languages)
        self._months = dict(self._locale.months)
        super(LocaleProxy, self).__init__()

    def __moyapy__(self):
        return self._locale

    def __repr__(self):
        return "<locale '{}'>".format(self._locale_name)

    def __str__(self):
        return self._locale_name

    @property
    def language(self):
        return self._locale.language

    @property
    def languages(self):
        return self._languages

    @property
    def territory(self):
        return self._locale.territory

    @property
    def language_name(self):
        return self._locale.get_language_name()

    @property
    def display_name(self):
        return self._locale.get_display_name()

    @property
    def territory_name(self):
        return self._locale.get_territory_name()

    @property
    def territories(self):
        return self._territories

    @property
    def months(self):
        return self._months


@implements_to_string
class SiteInstance(AttributeExposer):

    __moya_exposed_attributes__ = ['base_content',
                                   'timezone',
                                   'user_timezone',
                                   'append_slash',
                                   'head_as_get',
                                   'language',
                                   'locale',
                                   'datetime_format',
                                   'time_format',
                                   'date_format',
                                   'timespan_format',
                                   'translations',
                                   'host',
                                   'theme'
                                   ]

    def __init__(self, site, site_data, custom_data, _as_bool=lambda t: t.strip().lower() in ('yes', 'true')):
        self._site = site
        self._data = SettingsContainer.from_dict(custom_data)

        get = site_data.get
        self.base_content = get('base_content')
        self.timezone = get('timezone')
        self.user_timezone = _as_bool(get('user_timezone', 'no'))
        self.append_slash = _as_bool(get('append_slash', 'no'))
        self.head_as_get = _as_bool(get('head_as_get', 'yes'))
        self.language = get('language')
        _locale = get('locale', 'en')
        if _locale == 'auto':
            _locale, _ = locale.getdefaultlocale()
            # TODO: May not be correct on Windows
            # http://stackoverflow.com/questions/3425294/how-to-detect-the-os-default-language-in-python
        try:
            self.locale = LocaleProxy(_locale)
        except:
            log.error("unable to get locale '%s', defaulting to 'en'", _locale)
            self.locale = LocaleProxy('en')
        self.datetime_format = get('datetime_format')
        self.time_format = get('time_format')
        self.date_format = get('date_format')
        self.timespan_format = get('timespan_format')
        self.translations = gettext.NullTranslations()
        self.host = get('host')
        self.theme = get('theme')

    def __str__(self):
        return '''<site "{}">'''.format(self._site.domain)

    def __repr__(self):
        return "Site('{}')".format(self._site.domain)

    def __moyarepr__(self, context):
        return '''<site '{}'>'''.format(self._site.domain)

    def __moyaconsole__(self, console):
        console.text(text_type(self), fg="green", bold=True)
        table = sorted([(k, getattr(self, k)) for k in self.__moya_exposed_attributes__])
        console.table(table, header_row=['key', 'value'])


@implements_to_string
class Site(object):
    """Site data associated with a domain"""

    _re_domain = re.compile(r'(\*)|(\{.*?\})|(.*?)')
    _re_named_match = re.compile(r'{.*?}').match

    def __init__(self,
                 domain,
                 insert_order=0,
                 site_data=None,
                 custom_data=None):
        self.domain = domain
        if site_data is None:
            site_data = {}
        if custom_data is None:
            custom_data = None

        if 'priority' in site_data:
            _priority = site_data['priority']
            try:
                priority = int(_priority)
            except ValueError:
                startup_log.error("priority in site section should should be an integer (not '{}')".format(_priority))
        else:
            priority = 0
        self.order = (priority, insert_order)

        self.site_data = site_data
        self.custom_data = custom_data

        tokens = []
        for token in self._re_domain.split(domain):
            if token:
                if self._re_named_match(token):
                    name = token[1:-1]
                    if name.startswith('*'):
                        name = name[1:]
                        if name:
                            tokens.append('(?P<{}>.*?)'.format(re.escape(name)))
                        else:
                            tokens.append('(?:.*?)'.format(re.escape(name)))
                    else:
                        if name:
                            tokens.append('(?P<{}>[\w-]*?)'.format(re.escape(name)))
                        else:
                            tokens.append('(?:[\w-]*?)'.format(re.escape(name)))
                else:
                    if token == '*':
                        tokens.append('.*?')
                    else:
                        tokens.append(re.escape(token))
        re_domain = '^{}$'.format(''.join(tokens))
        self._match = re.compile(re_domain).match

    def __str__(self):
        return '''<site "{}">'''.format(self.domain)

    def __repr__(self):
        return "Site('{}', {!r})".format(self.domain, self.site_data)

    def __moyarepr__(self, context):
        return '''<site '{}', {}>'''.format(self.domain, context.to_expr(self.site_data))

    def match(self, domain):
        match = self._match(domain)
        if match is None:
            return None, None
        match_dict = match.groupdict()
        site_data = self.site_data.copy()
        custom_data = self.custom_data.copy()
        site_data.update(match_dict)
        custom_data.update(match_dict)
        return site_data, custom_data


class Sites(object):
    """A container that maps site wild-cards on to a dictionary"""

    _site_keys = [("base_content", 'site#content.base'),
                  ("timezone", 'UTC'),
                  ("user_timezone", 'yes'),
                  ("append_slash", 'no'),
                  ("locale", 'en_us.UTF-8'),
                  ("language", 'en-US'),
                  ("datetime_format", 'medium'),
                  ("date_format", 'medium'),
                  ("time_format", 'medium'),
                  ("timespan_format", 'medium'),
                  ("host", "${.request.host_url}"),
                  ("theme", "default")]

    def __init__(self):
        self._defaults = {}
        self._sites = []
        self._order = 0

    def __repr__(self):
        return repr(self._sites)

    def clear(self):
        """Clear all site information"""
        del self._sites[:]

    def set_defaults(self, section):
        self._defaults = {k: section.get(k, default) for k, default in self._site_keys}

    def add_from_section(self, domains, section):
        """Add a site from a named section in settings"""
        site_data = self._defaults.copy()
        custom_data = {}
        for k, v in iteritems(section):
            prefix, hyphen, key = k.partition('-')
            if hyphen and prefix in ('data', ''):
                custom_data[key] = v
            else:
                site_data[k] = v

        for domain in domains.split(','):
            domain = domain.strip()
            site = Site(domain, self._order, site_data=site_data, custom_data=custom_data)
            self._order += 1
            self._sites.append(site)

    def add(self, domains, **data):
        if isinstance(domains, text_type):
            domains = domains.split(',')
        for domain in domains:
            domain = domain.strip()
            site = Site(domain, self._order, custom_data=data)
            self._order += 1
            self._sites.append(site)

    def _match(self, domain):
        self._sites.sort(key=lambda s: s.order, reverse=True)
        for site in self._sites:
            site_data, custom_data = site.match(domain)
            if site_data is not None:
                return SiteMatch(site, site_data, custom_data)
        return None

    def match(self, domain, context=None):
        site_match = self._match(domain)
        if site_match is None:
            return None
        site, site_data, custom_data = site_match
        if context is None:
            return custom_data
        sub = context.sub
        with context.data_frame(site_data):
            new_site_data = {k: sub(v) for k, v in site_data.items()}
        with context.data_frame(custom_data):
            new_custom_data = {k: sub(v) for k, v in custom_data.items()}
        return SiteInstance(site, new_site_data, new_custom_data)

    def __contains__(self, domain):
        return self.match(domain) is not None


if __name__ == "__main__":

    sites = Sites()
    sites.add("www.moyaproject.com", name="www")
    sites.add('moyaproject.com', name="nodomain")
    sites.add('{name}.moyaroject.com', subdomain=True)
    sites.add('127.*', local=True)

    print(1, sites.match('www.moyaroject.com'))
    print(2, sites.match('moyaroject.com'))
    print(3, sites.match('blog.moyaroject.com'))
    print(4, sites.match('127.0.0.1'))
    print(5, sites.match('google.com'))

    print('moyaroject.com' in sites)
    print('google.com' in sites)

    print(sites)

    print(Site('{*subdomain}.{domain}.{tld}').match('sub.sub-domain.moyaroject.com'))

    sites = Sites()
    sites.add('www.moyaroject.com,blog.moyaroject.com')

    sites = Sites()
    sites.add('*')
    print(sites.match('alternative.localhost'))

    sites = Sites()
    sites.add('{*domain}', name="test")
    print(sites.match('www.moyaproject.com'))
