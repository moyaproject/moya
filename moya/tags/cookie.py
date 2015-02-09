from __future__ import unicode_literals
from ..elements import Attribute
from ..elements.elementbase import LogicElement
from ..context.expressiontime import to_seconds


class CookieJar(dict):
    """A container for cookies"""

    def __init__(self, *args, **kwargs):
        self.deleted_cookies = set()
        super(CookieJar, self).__init__(*args, **kwargs)

    def __moyaconsole__(self, console):
        console.text("These are pending cookies that Moya will send with the response")
        from ..console import Cell
        table = [[Cell('name'),
                  Cell('value'),
                  Cell('path'),
                  Cell('domain'),
                  Cell('secure?')]]
        for cookie in self.itervalues():
            if isinstance(cookie, Cookie):
                table += [cookie.name,
                          cookie.value,
                          cookie.path,
                          cookie.domain,
                          'Y' if cookie.secure else 'N'
                          ]
        console.table(table)

    def __delitem__(self, key):
        self.deleted_cookies.add(key)
        super(self, '__delitem__')(key)


class Cookie(object):
    """Stores incoming cookies"""
    def __init__(self, name, value, max_age, path, domain, secure, httponly, comment, overwrite):
        self.name = name
        self.value = value
        self.max_age = max_age
        self.path = path
        self.domain = domain
        self.secure = secure
        self.httponly = httponly
        self.comment = comment
        self.overwrite = overwrite

    def __repr__(self):
        return "<cookie {} {!r}>".format(self.name, self.value)

    def set(self, response):
        response.set_cookie(self.name,
                            self.value,
                            max_age=self.max_age,
                            path=self.path,
                            domain=self.domain,
                            secure=self.secure,
                            httponly=self.httponly,
                            comment=self.comment,
                            overwrite=self.overwrite)


class SetCookie(LogicElement):
    """Set a new cookie."""

    class Help:
        synopsis = "set a cookie"
        example = """
            <set-cookie name="session" value="${session.key}" overwrite="yes" />
        """

    name = Attribute("Cookie name")
    value = Attribute("Value", required=True)
    maxage = Attribute("Max age of cookie (in seconds or as timespan)",
                       metavar="AGE",
                       type="timespan",
                       required=False,
                       example="60m")
    path = Attribute("Path", required=False, default="/", metavar="PATH")
    domain = Attribute("Domain", required=False, default=None, metavar="DOMAIN")
    secure = Attribute("Secure", type="boolean", default=False)
    httponly = Attribute("HTTP Only?", type="boolean", required=False, default=False)
    comment = Attribute("Comment", required=False, default=None)
    overwrite = Attribute("Overwrite?", required=False, default=False)

    def logic(self, context):
        params = self.get_parameters(context)
        cookie = Cookie(params.name,
                        params.value,
                        to_seconds(params.maxage),
                        params.path,
                        params.domain,
                        params.secure,
                        params.httponly,
                        params.comment,
                        params.overwrite)
        context.root['cookiejar'][params.name] = cookie


class DeleteCookie(LogicElement):
    """Delete a previously set cookie."""

    class Help:
        synopsis = "delete a cookie"
        example = """
            <delete-cookie name="authsession" />
        """

    name = Attribute("Cookie name")

    def logic(self, context):
        try:
            context.root['cookiejar'][self.name(context)]
        except KeyError:
            pass
