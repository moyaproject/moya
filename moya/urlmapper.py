from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from . import pilot
from .containers import LRUCache
from .syntax import highlight
from .compat import implements_to_string, implements_bool, text_type, iteritems
from .console import ConsoleHighlighter
from .context.tools import to_expression

import re
import threading
from collections import namedtuple, defaultdict
from operator import attrgetter
from .compat import quote

from pyparsing import Literal, QuotedString, Word, OneOrMore, printables, ParseException
import pyparsing
pyparsing.ParserElement.enablePackrat()


class URLHighlight(ConsoleHighlighter):
    styles = {
        None: "bold blue",
        "asterix": "bold yellow",
        "param": "bold magenta"
    }

    highlights = [
        r'(?P<param>\{.*?\})',
        r'(?P<asterix>\*)',
    ]


class TargetHighlight(ConsoleHighlighter):
    styles = {
        "lib": "bold blue",
        "name": "bold green",
        "hash": "white"
    }

    highlights = [
        r'(?P<lib>.*?)(?P<hash>#)(?P<name>.*?)[,\s$]',
    ]


class RouteError(ValueError):
    hide_py_traceback = True


class DuplicatedParameter(RouteError):
    """a url parameter was repeated"""


class MissingURLParameter(RouteError):
    """A parameter in a route was not supplied"""


class NamedURLNotFound(RouteError):
    """No such named route exists"""


def _router_grammer():
    """Make the url route grammer"""
    wildcard = Literal('*')
    path_separator = Literal('/').setParseAction(lambda t: ('sep', t))
    extract = QuotedString(quoteChar='{', endQuoteChar='}').setParseAction(lambda t: ('extract', t))
    static = Word(''.join(c for c in printables if c not in '?{}/')).setParseAction(lambda t: ('static', t))
    route_parse = OneOrMore(extract | static | path_separator | wildcard)
    return route_parse

RouteMatch = namedtuple("RouteMatch", ["data", "target", "name"])


@implements_to_string
@implements_bool
class URLProxy(object):

    def __init__(self, mapper, path=None):
        self.mapper = mapper
        if path is None:
            path = []
        self.path = path
        self.bound = None

    @classmethod
    def url_join(self, url_parts, from_root=False, _consecutive_slashes_sub=re.compile(r'/+').sub):
        url = _consecutive_slashes_sub('/', ''.join(url_parts))
        if from_root and not url.startswith('/'):
            return '/' + url
        return url

    def bind(self, data):
        self.bound = data

    def __getitem__(self, name):
        obj = self.evaluate()
        if isinstance(obj, text_type):
            return obj[name]
        if name not in obj.named_routes:
            raise KeyError(name)
        proxy = URLProxy(self.mapper, self.path + [name])
        #obj = proxy.evaluate()
        #if isinstance(obj, text_type):
        #    return obj
        return proxy

    def __moyacall__(self, params):
        self.bound = params
        return self

    def __str__(self):
        obj = self.evaluate()
        if isinstance(obj, text_type):
            return obj
        else:
            return self.base_url

    def __repr__(self):
        return "<urlproxy>"

    def __moyarepr__(self, context):
        obj = self.evaluate()
        if isinstance(obj, text_type):
            return to_expression(context, obj)
        base_url = self.base_url
        if base_url is None:
            return "<mapper>"
        else:
            return "<mapper '{}'>".format(base_url)

    def keys(self):
        obj = self.evaluate()
        if isinstance(obj, text_type):
            return []
        return sorted(obj.named_routes.keys())

    def values(self):
        return [self[k] for k in self.keys()]

    def items(self):
        return zip(self.keys(), self.values())

    def __len__(self):
        return len(self.keys())

    def __contains__(self, k):
        obj = self.evaluate()
        if isinstance(obj, text_type):
            return k in obj
        return k in obj.named_routes

    # This class is a bit schitzo; it can behave like a list or a string
    def __bool__(self):
        obj = self.evaluate()
        if isinstance(obj, text_type):
            return bool(obj)
        return bool(obj.named_routes)

    @property
    def base_route(self):
        mapper = self.mapper
        url_route = []
        for name in self.path:
            route = mapper.named_routes[name][0]
            url_route.append(route._route)
            if isinstance(route.target, URLMapper):
                mapper = route.target
            else:
                break
        return self.url_join(url_route, from_root=True)

    @property
    def base_url(self):
        if self.bound is None:
            data = pilot.context
        else:
            data = self.bound
        mapper = self.mapper
        url_parts = []
        for name in self.path:
            route = mapper.named_routes[name][0]
            if isinstance(route.target, URLMapper):
                url_parts.append(route.generate(data)[1])
                mapper = route.target
            else:
                break
        return self.url_join(url_parts, from_root=True)

    def evaluate(self):
        if self.bound is None:
            data = pilot.context
        else:
            data = self.bound
        mapper = self.mapper
        url_parts = []
        for name in self.path:
            route = mapper.named_routes[name][0]
            if isinstance(route.target, URLMapper):
                url_parts.append(route.generate(data)[1])
                mapper = route.target
            else:
                url_parts.append(route.generate(data)[1])
                url = self.url_join(url_parts, from_root=True)
                return url
        return mapper

    def __moyaconsole__(self, console):
        _mapper = self.evaluate()
        if isinstance(_mapper, text_type):
            console.obj(pilot.context, _mapper)
            return

        table = []
        console("URL mapper on ", fg="blue", bold=True)(text_type(self.base_route), bold=True, fg="cyan").nl()
        for mapper in _mapper.routes:
            name = mapper.name
            if isinstance(mapper.target, (list, tuple)):
                target_type = "final"
                str_target = ", ".join(mapper.target)
                mount = mapper.route
            else:
                mount = mapper.route
                target_type = "mountpoint"
                str_target = ''
            table.append([name or '', target_type, self.url_join([self.base_url, mount]), str_target])
        console.table(table,
                      header_row=["name", "type", "route", "target"],
                      cell_processors={2: URLHighlight.highlight, 3: TargetHighlight.highlight})

    def __moyarenderable__(self, context):
        request = context['.request']
        renderable = []

        def recurse_urlmapper(mapper, url_parts=None, app=None):
            if url_parts is None:
                url_parts = ['/']
            for mapper in mapper.routes:
                if not mapper.match_method(request.method, None):
                    continue
                methods = ', '.join(mapper.methods or ['*'])

                if isinstance(mapper.target, (list, tuple)):
                    mount = mapper.route
                    url = self.url_join(url_parts + [mount])
                    url = highlight("route", url, line_numbers=False)

                    targets = [(target, highlight("target", target, line_numbers=False))
                               for target in mapper.target]

                    renderable.append([url, methods, app, targets])
                else:
                    url = self.url_join(url_parts + [mapper.route])
                    _, params = mapper.partial_parse(url)
                    app = params.get('app', app) if params else None
                    recurse_urlmapper(mapper.target, url_parts + [mapper.route], app=app)

        recurse_urlmapper(self.mapper)
        return renderable


class _NamedURLs(object):
    """Retrieves named urls a mapper and its descendants"""

    def __init__(self, mapper, cache_size=10000):
        self.mapper = mapper
        self.named_routes = self._get_named_routes()
        self.cache = LRUCache(cache_size)

    def __repr__(self):
        return "<namedurls '{}'>".format(self.mapper.name)

    def _get_named_routes(self):
        named_routes = defaultdict(list)

        def recurse_mapper(mapper, path):
            for route in mapper.routes:
                target = route.target
                if isinstance(target, URLMapper):
                    recurse_mapper(target, path + (route,))
                else:
                    if route.name is not None:
                        named_routes[route.name].append(path + (route,))
        recurse_mapper(self.mapper, ())

        return named_routes

    def get_url(self, name, params=None, route=None):
        if params is None:
            params = {}
        cache_key = (id(route), name, tuple(sorted(params.items())))
        cached_url = self.cache.get(cache_key, None)
        if cached_url is not None:
            return cached_url

        matches = []
        for i, path in enumerate(self.named_routes[name]):
            if route is not None:
                path = (route,) + path
            try:
                remaining_params, url = self._reverse_url_path(path, params)
            except MissingURLParameter:
                # This path requires a url parameter that we don't have
                continue
            else:
                matches.append((remaining_params, i, url))

        if matches:
            matches.sort()
            url = matches[0][-1]
            self.cache[cache_key] = url
            return url

        if params:
            params_display = ",".join("{}='{}'".format(k, v) for k, v in iteritems(params))
            raise NamedURLNotFound("No matching URL with name '{}' and parameters {}".format(name, params_display))
        else:
            raise NamedURLNotFound("No matching URL with name '{}' and no parameters".format(name))

    def _reverse_url_path(self, path, params, _consecutive_slashes_sub=re.compile(r'/+').sub):
        url_components = []
        path_matched = set()
        for route in path:
            matched, url = route.generate(params)
            path_matched.update(matched)
            url_components.append(url)
        url = _consecutive_slashes_sub('/', ''.join(url_components))
        if not url.startswith('/'):
            url = '/' + url
        return len(params) - len(path_matched), url


class URLMapper(object):

    def __init__(self, name=''):
        self.name = name
        self._routes = []
        self._route_cache = LRUCache(1000)
        self._named_routes = defaultdict(list)
        self._named_urls = None
        self._proxy = None
        self._insert_order = 0
        self._finalized = False

    def __repr__(self):
        if self.name:
            return "<urlmapper '{}'>".format(self.name)
        else:
            return "<urlmapper>"

    def __moyacontext__(self, context):
        if self._proxy is None:
            self._proxy = URLProxy(self)
        return self._proxy

    @property
    def routes(self):
        self.finalize()
        return self._routes

    @property
    def named_routes(self):
        self.finalize()
        return self._named_routes

    def _get_order(self, priority):
        """Get a tuple for use as a route order attribute"""
        order = (-priority, self._insert_order)
        self._insert_order += 1
        return order

    def finalize(self, _get_order=attrgetter('order')):
        """Finalize the url mapper (does sorting)"""
        if not self._finalized:
            self._finalized = True
            self._routes.sort(key=_get_order)
            for k, v in iteritems(self._named_routes):
                v.sort(key=_get_order)

    @property
    def named_urls(self):
        if self._named_urls is None:
            self._named_urls = _NamedURLs(self)
        return self._named_urls

    def map(self, url, target, methods=None, handlers=None, defaults=None, name=None, priority=0, final=False):
        """Map a url on to a target object."""
        route = Route(self,
                      url,
                      partial=False,
                      defaults=defaults or {},
                      methods=methods,
                      handlers=handlers,
                      target=target,
                      name=name,
                      order=self._get_order(priority),
                      final=final)
        try:
            route.re_route
        except ParseException as e:
            raise ValueError("failed to parse route, {}".format(text_type(e).lower()))
        self._routes.append(route)
        if name is not None:
            self._named_routes[name].append(route)
        self._finalized = False
        return route

    def mount(self, url, mapper, defaults=None, name=None, priority=0):
        """Mount a sub-mapper on a url."""
        if url:
            if not url.startswith('/'):
                url = '/' + url
            if not url.endswith('/'):
                url += '/'
        route = Route(self,
                      url,
                      partial=True,
                      defaults=defaults or {},
                      target=mapper,
                      methods=None,
                      name=name,
                      order=self._get_order(priority))
        if name is not None:
            self._named_routes[name].append(route)
        self._routes.append(route)
        self._finalized = False
        return route

    def get_routes(self, name, default=Ellipsis):
        routes = self.named_routes.get(name, default)
        if routes is Ellipsis:
            raise RouteError("Named route '{}' not found".format(name))
        return routes

    def get_route(self, url, method="GET", handler=None):
        """Process a URL for any corresponding routes"""
        for route_match in self.iter_routes(url, method, handler):
            return route_match
        return None

    def iter_routes(self, url, method="GET", handler=None):
        """Yield any routes that match the url"""

        route_key = (url, method, handler)

        if route_key in self._route_cache:
            route_matches = self._route_cache.lookup(route_key)

        else:
            self.finalize()
            route_matches = []
            add_route_match = route_matches.append
            for route in self._routes:
                if route.match_method(method, handler):
                    if route.partial:
                        remaining_url, url_data = route.partial_parse(url)
                        if remaining_url is None:
                            continue
                        if not remaining_url.startswith('/'):
                            remaining_url = '/' + remaining_url
                        sub_url_router = route.target
                        for route_match in sub_url_router.iter_routes(remaining_url,
                                                                      method=method,
                                                                      handler=handler):
                            sub_url_data = url_data.copy()
                            sub_url_data.update(route_match.data)
                            add_route_match(RouteMatch(sub_url_data, route_match.target, route_match.name))
                    else:
                        route_data = route.parse(url)
                        if route_data is not None:
                            add_route_match(RouteMatch(route_data, route.target, route.name))
                            if route.final:
                                break

            self._route_cache[route_key] = route_matches
        return iter(route_matches)

    def has_route(self, url, method="GET", handler=None):
        for route in self.iter_routes(url, method, handler):
            return True
        return False

    def get_url(self, name, params=None, base_route=None):
        return self.named_urls.get_url(name, params, route=base_route)

    def render(self, level=0):
        for route in self.routes:
            print('    ' * level + repr(route))
            if isinstance(route.target, URLMapper):
                route.target.render(level + 1)


@implements_to_string
class Route(object):
    """Parses URLs and extracts parameters from them"""

    _route_parse = _router_grammer()

    _patterns = {'': (r"[^/]+?", lambda s: s),
                 '*': (r".*?", lambda s: s),
                 'alpha': (r"[a-zA-Z0-9]+?", lambda s: s),
                 'slug': (r"[\w_-]+?", lambda s: s),

                 "integer": (r"\-?\d+?", int),
                 "float": (r"\-?\d+\.\d+", float),

                 "posinteger": (r"\d+?", int),
                 "posfloat": (r"\d+\.\d+", float)
                 }

    def __init__(self,
                 mapper,
                 route,
                 partial=False,
                 defaults={},
                 methods=None,
                 handlers=None,
                 target=None,
                 name=None,
                 order=(0, 0),
                 final=False):
        self.mapper = mapper
        self._route = route
        self.route = route
        self.partial = partial
        self.defaults = defaults
        self.methods = methods
        self.handlers = handlers or []
        self.target = target
        self.name = name
        self.order = order
        self.final = final

        self.component_names = []
        self.component_callables = {}
        self.handlers = [int(handler) for handler in self.handlers]
        self._tokens = None
        self._re_route = None

        self._lock = threading.Lock()

    @property
    def tokens(self):
        if self._tokens is None:
            self._tokens = ([(tt, t[0])
                            for (tt, t) in self._route_parse.parseString(self._route, True)]
                            if self._route else [])
        return self._tokens

    @classmethod
    def _split_pattern_name(cls, token):
        if ':' in token:
            return token.split(':', 1)
        return '', token

    @property
    def re_route(self):
        with self._lock:
            if not self._re_route:
                segments = ['^']
                append_segment = segments.append
                escape = re.escape
                static = True
                default_pattern = self._patterns.get('')
                for token_type, token in self.tokens:
                    if token_type == 'extract':
                        static = False
                        if token.startswith('*'):
                            pattern_name, name = self._split_pattern_name(token[1:])
                            pattern, component_callable = self._patterns.get(pattern_name or '*', default_pattern)
                            if name:
                                if name in self.component_names:
                                    raise DuplicatedParameter("URL parameter '{}' was duplicated".format(name))
                                append_segment('(?P<%s>%s)' % (name, pattern))
                            else:
                                append_segment('(.*)')
                            self.component_names.append(name)
                        else:
                            pattern_name, name = self._split_pattern_name(token)
                            pattern, component_callable = self._patterns.get(pattern_name, default_pattern)
                            append_segment('(?P<%s>%s)' % (name, pattern))
                            if name in self.component_names:
                                raise DuplicatedParameter("URL parameter '{}' was duplicated".format(name))
                            self.component_names.append(name)
                        self.component_callables[name] = component_callable
                    else:
                        if token == '*':
                            append_segment('.*?')
                        else:
                            append_segment(escape(token))

                if not self.partial:
                    append_segment('$')

                self.static = static
                self.re_route_text = ''.join(segments)
                self._re_route = None
                self._re_route = re.compile(self.re_route_text)

            return self._re_route

    def __str__(self):
        if isinstance(self.target, tuple):
            target = ", ".join(self.target)
        else:
            target = str(self.target)
        if self.handlers:
            m = ",".join(text_type(h) for h in self.handlers)
        else:
            m = ','.join(self.methods or ['*'])

        return "<route '%s' %s %s: %s>" % (self.name, m, self.route, target)

    def __repr__(self):
        if isinstance(self.target, tuple):
            target = ", ".join(self.target)
        else:
            target = str(self.target)
        m = ','.join(self.methods or ['*'])
        return "<route '%s' %s %s:%s>" % (self.name, m, self.route, target)

    def update_defaults(self, defaults):
        """Update URL route defaults"""
        self.defaults.update(defaults)

    def match_method(self, method, handler):
        if self.handlers:
            if handler is None:
                return False
            return handler in self.handlers
        if handler:
            if self.partial:
                return True
            return False
        return (self.methods is None or
                method == '*' or
                method in self.methods)

    def parse(self, url):
        """Parse a URL and return a dictionary containing parameters"""
        match = self.re_route.match(url)
        null_callable = lambda v: v
        get_component_callable = self.component_callables.get
        if match:
            m = self.defaults.copy()
            m.update(match.groupdict())
            try:
                m = dict((k, get_component_callable(k, null_callable)(v))
                         for k, v in m.items())
            except ValueError:
                return None
            return m
        return None

    def partial_parse(self, url):
        """Parses a URL as far as possible and returns a tuple of the remaining portion of the URL
        and the parsed parameters.

        """
        params = self.parse(url)
        if params is None:
            return None, None
        params = params or {}
        partial_url = self.generate(params)[1]
        remaining_url = url[len(partial_url):]
        return remaining_url, params

    def generate(self, component_map, remove=False):
        """Recreate a URL from the given parameters"""
        self.re_route
        if self.static:
            return set(), self.route

        matched = set()
        segments = []
        append = segments.append
        url_params = self.defaults.copy()

        for name in self.component_names:
            if name in component_map:
                matched.add(name)
                url_params[name] = component_map[name]

        for token_type, token in self.tokens:
            if token_type == "extract":
                try:
                    name = token.lstrip('*')
                    if ':' in name:
                        _, name = name.split(':', 1)
                    append(url_params[name])
                except KeyError:
                    raise MissingURLParameter("Can't generate URL without a value for '{}'".format(name))
            else:
                append(token)
        return matched, ''.join(quote(text_type(s)) for s in segments)

    # def reverse_url(self, params):
    #     components = []
    #     route = self
    #     while route:
    #         components.append(route.generate(params))
    #         if route.mapper is None:
    #             break
    #         route = route.mapper.route
    #     url = ''.join(reversed(components)).replace('//', '/')
    #     if not url.startswith('/'):
    #         url = '/' + url
    #     return url

    # def reverse_url_path(self, path, params):
    #     components = [route.generate(params) for route in path]
    #     url = ''.join(components).replace('//', '/')
    #     if not url.startswith('/'):
    #         url = '/' + url
    #     return url


if __name__ == "__main__":
    mapper = URLMapper('server')

    uploads_mapper = URLMapper('uploads')
    media_mapper = URLMapper('media')

    static_mapper = URLMapper('static')
    static_mapper.map('/{*path}/', '#server', name="serve")

    uploads_mapper.mount('/uploads/', static_mapper, name="uploads")
    media_mapper.mount('/static/', static_mapper, name="static")

    uploads_mapper.render()
    media_mapper.render()

    print(uploads_mapper.get_url('serve', {'path': "css/content.css"}))
    #import rpdb2; rpdb2.start_embedded_debugger('password')
    print(media_mapper.get_url('serve', {'path': "css/content.css"}))
