from __future__ import unicode_literals
from __future__ import print_function

from .interface import AttributeExposer
from .compat import iteritems, implements_to_string

from babel import Locale

import gettext
import re
from collections import namedtuple
import logging
log = logging.getLogger('moya.runtime')


SiteMatch = namedtuple("SiteMatch", ["site", "data"])


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
class Site(object):
    """Site data associated with a domain"""

    _re_domain = re.compile(r'(\*)|(\{.*?\})|(.*?)')
    _re_named_match = re.compile(r'{.*?}').match

    def __init__(self,
                 domain,
                 base_content='site#content.base',
                 timezone='UTC',
                 user_timezone=True,
                 append_slash=True,
                 language='en-US',
                 locale='en_US.UTF-8',
                 datetime_format='medium',
                 date_format='medium',
                 time_format='medium',
                 timespan_format='medium',
                 data=None):
        self.domain = domain

        self.base_content = base_content
        self.timezone = timezone
        self.user_timezone = user_timezone
        self.append_slash = append_slash
        self.language = language
        try:
            self.locale = LocaleProxy(locale)
        except:
            log.error("Unable to get locale '{}', defaulting to 'en'")
            self.locale = LocaleProxy('fr')
        self.datetime_format = datetime_format
        self.time_format = time_format
        self.date_format = date_format
        self.timespan_format = timespan_format
        self.translations = gettext.NullTranslations()

        if data is None:
            data = {}
        self.site_data = data
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

    def match(self, domain):
        match = self._match(domain)
        if match is None:
            return None
        data = self.site_data.copy()
        data.update(match.groupdict())
        return data


class Sites(object):
    """A container that maps site wild-cards on to a dictionary"""

    def __init__(self):
        self._sites = []

    def __repr__(self):
        return repr(self._sites)

    def set_defaults(self, section):
        self.base_content = section.get('base_content', 'site#content.base')
        self.timezone = section.get('timezone', 'UTC')
        self.user_timezone = section.get_bool('user_timezone', True)
        self.append_slash = section.get_bool('append_slash', False)
        self.locale = section.get('locale', 'en_US.UTF-8')
        self.language = section.get('language', 'en-US')
        self.datetime_format = section.get('datetime_format', 'medium')
        self.date_format = section.get('date_format', 'medium')
        self.time_format = section.get('time_format', 'medium')
        self.timespan_format = section.get('timespan_format', 'medium')

    def add_from_section(self, domains, section):
        """Add a site from a named section in settings"""
        kwargs = {
            "base_content": section.get('base_content', self.base_content),
            "timezone": section.get('timezone', self.timezone),
            "user_timezone": section.get_bool('user_timezone', self.user_timezone),
            "append_slash": section.get('append_slash', self.append_slash),
            "language": section.get('language', self.language),
            "locale": section.get('locale', self.locale),
            "datetime_format": section.get('datetime_format', self.datetime_format),
            "date_format": section.get('date_format', self.date_format),
            "time_format": section.get('time_format', self.time_format),
            'timespan_format': section.get('timespan_format', self.timespan_format)
        }
        data = {}
        for k, v in iteritems(section):
            if k.startswith('data-'):
                data_k = k.split('-', 1)[1]
                data[data_k] = v

        for domain in domains.split(','):
            domain = domain.strip()
            site = Site(domain, data=data, **kwargs)
            self._sites.append(site)

    def add(self, domains, **data):
        for domain in domains.split(','):
            domain = domain.strip()
            site = Site(domain, data=data)
            self._sites.append(site)

    def match(self, domain):
        for site in self._sites:
            site_data = site.match(domain)
            if site_data is not None:
                return SiteMatch(site, site_data)
        return None

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
