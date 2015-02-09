from __future__ import unicode_literals
from ..elements.elementbase import ElementBase, LogicElement, Attribute
from ..tags.context import DataSetter
from ..tools import asint
from .. import logic
from .. import errors
from ..elements.attributetypes import *
from ..contextenum import ContextEnum
from ..compat import iteritems, text_type

from fs.path import pathjoin
from fs.opener import fsopendir

from os.path import dirname, abspath
import sys
import textwrap
from time import time

import pytz

import logging
log = logging.getLogger('moya.runtime')
startup_log = logging.getLogger('moya.startup')
runtime_log = logging.getLogger('moya.runtime')


class Moya(ElementBase):
    """This is the root element for Moya files."""
    version = Attribute("""version number of this Moya file (currently ignored, if supplied use "1.0")""", type="version", required=False,)

    class Help:
        synopsis = """begin a Moya file"""
        example = """
        <moya xmlns="http://moyaproject.com">
            <!-- Ready for take off -->
        </moya>

        """


class ConfigElement(ElementBase):

    class Help:
        undocumented = True

    def execute(self, archive, context, fs):
        pass


class Breakpoint(LogicElement):
    """Stops the execute of Moya code and drops in to the debugger."""

    class Help:
        synopsis = """drop in to the debugger"""
        example = """

        <!-- drop in to the debugger -->
        <breakpoint/>

        <for src="-100..100" dst="count">
            <!-- Conditional breakpoint with 'if' attribute -->
            <breakpoint if="count==0"/>
            <!-- This throws an exception when count is 0 -->
            <echo>${1/count}<echo>
        </for>

        """

    def logic(self, context):
        raise logic.DebugBreak(self)


class Import(LogicElement):
    """Import a library. Importing reads the XML associated with a library and makes it available to be installed as an application. This tag must appear within a [tag]server[/tag] tag.

    Libraries can be installed either from a Python module, or directly from a path. For example, this installs a library from a Python module:

    [code xml]
    <import py="moya.libs.auth"/>
    [/code]

    And this installs a library from a a relative path:

    [code xml]
    <import location="./local/sushishop/" />
    [/code]

    The [c]priority[/c] attribute is used when two element have the same element reference. This is typically used to override an element in another library. For example, let's say we have the following [tag]macro[/tag] in a library called [c]sushifinder.shop[/c], which calculate tax on a shopping cart:

    [code xml]
    <macro libname="macro.get_tax">
        <!-- calculate tax for an order-->
    </macro>
    [/code]

    We could replace this by defining the following in another library:

    [code xml]
    <macro libname="sushifinder.shop#macro.get_tax">
        <!-- custom tax calculator -->
    </macro>
    [/code]

    Note the use of a full element reference (including library name) in the [c]libname[/c] attribute. This tells Moya that the macro should go in a library other than the one it was declared in. If the code above is in a library with a higher priority then it will replace the macro in the [c]sushifinder.shop[/c] library.

    The [c]templatepriority[/c] is used when there are conflicting template paths. The template from the library with the highest priority wins. This value takes precedence over the [c]priority[/c] defined in [link library#lib-section]lib.ini[/link].


    """

    class Help:
        synopsis = """import a library"""

    name = Attribute("Name of the library")
    location = Attribute("A path to a Moya library")
    py = Attribute("Python import, e.g. widgets.moya.widgetapp")
    priority = Attribute("Priority for elements", type="integer", required=False, default=None)
    templatepriority = Attribute("Priority for templates", type="integer", required=False, default=None)

    def logic(self, context):
        start = time()
        (name,
         _location,
         py,
         priority,
         template_priority) = self.get_parameters(context,
                                                  'name',
                                                  'location',
                                                  'py',
                                                  'priority',
                                                  'templatepriority')
        archive = self.document.archive
        absolute = False
        if _location is not None:
            location = _location
        else:
            if py in sys.modules:
                reload(sys.modules[py])
            try:
                __import__(py)
            except ImportError as e:
                raise errors.ElementError("unable to import Python module '{}'".format(py),
                                          element=self,
                                          diagnosis=text_type(e))
            module = sys.modules[py]
            location = dirname(abspath(module.__file__))
            absolute = True

        if '::/' in location:
            import_fs = fsopendir(location)
        else:
            if absolute:
                import_fs = fsopendir(location)
            else:
                project_fs = context['fs']
                if project_fs.hassyspath('/'):
                    project_path = project_fs.getsyspath('/')
                    import_path = pathjoin(project_path, location)
                    import_fs = fsopendir(import_path)
                else:
                    import_fs = context['fs'].opendir(location)
        lib = archive.load_library(import_fs,
                                   priority=priority,
                                   template_priority=template_priority,
                                   long_name=name,
                                   rebuild=context.root.get('_rebuild', False))
        if lib.failed_documents:
            if _location is not None:
                msg = "Failed to load library '{}' from location '{}'"
                raise errors.StartupFailedError(msg.format(name or lib.long_name, _location))
            elif py:
                msg = "Failed to load library '{}' from Python module '{}'"
                raise errors.StartupFailedError(msg.format(name or lib.long_name, py))
            else:
                raise errors.StartupFailedError("Failed to load library '{}'".format(name or lib.long_name))
        startup_log.debug("%s imported %.1fms", lib, (time() - start) * 1000.0)
        if lib.priority:
            startup_log.debug("%s priority is %s", lib, lib.priority)
        if lib.template_priority:
            startup_log.debug("%s template priority is %s", lib, lib.template_priority)


class Install(LogicElement):
    """
    Installs an [i]application[/i]. An application is effectively an [i]instance[/i] of a library, with its own settings and serving content from unique URL(s). An [tag]install[/tag] tag should appear within a [tag]server[/tag] tag. A library must first be [i]imported[/i] (with [tag]import[/tag]) prior to installing.

    """

    class Help:
        synopsis = """create an application from a library"""
        example = """
        <install name="auth" lib="moya.auth" mount="/auth/"/>
        """

    lib = Attribute("Library long name (e.g. moya.auth)", required=True)
    name = Attribute("Name of the application (must not contain a dot), e.g. \"auth\"", required=True)
    mount = Attribute("URL component to mount, e.g. \"auth\"")
    mountpoint = Attribute("Name of the <mountpoint> tag", required=False, default="main")

    def logic(self, context):
        params = self.get_parameters(context)
        archive = self.document.archive
        try:
            self.archive.build_libs()
        except Exception as e:
            raise
        try:
            app = archive.create_app(params.name, params.lib)
        except errors.ArchiveError as e:
            raise errors.ElementError(text_type(e))
        if app.lib.failed_documents:
            raise errors.StartupFailedError("Unable to import lib '%s'" % params.lib)

        if params.mount:
            server = self.get_ancestor('server')
            try:
                mountpoint = app.lib.get_element_by_type_and_attribute("mountpoint", "name", params.mountpoint)
            except errors.ElementNotFoundError:
                return
                raise errors.StartupFailedError("No mountpoint called '{0}' in {1}".format(params.mountpoint, app.lib))
            app.mounts.append((params.mountpoint, params.mount))
            server.urlmapper.mount(params.mount,
                                   mountpoint.urlmapper,
                                   defaults={'app': app.name},
                                   name=params.name)

            for stage, urlmapper in iteritems(server.middleware):
                urlmapper.mount(params.mount,
                                mountpoint.middleware[stage],
                                defaults={'app': app.name},
                                name=params.name)
            startup_log.debug("%s installed, mounted on %s", app, params.mount)
        else:
            startup_log.debug("%s installed", app)


class Log(LogicElement):
    """Write text to the logs. Every line of text can have a [i]level[/i] which indicates how significant the message is. Log levels can be filtered, so you only see relevant messages.

    You can control which log messages are written via [c]logging.ini[/c].
    """

    class Help:
        synopsis = """write information to the log"""
        example = """

        <log level="debug">This may help you track down errors</log>
        <log>Something worth knowing happened</log> <!-- default log level is "info" -->
        <log level="warning">Pay attention, this may be significant</log>
        <log level="error">Something quite alarming happened</log>
        <log level="fatal">Absolute disaster</log>

        """

    _levels = {
        "debug": 10,
        "info": 20,
        "warn": 30,
        "warning": 30,
        "error": 40,
        "fatal": 50
    }
    _default_level = "info"

    level = Attribute('''Logging level''',
                      default=None,
                      choices=_levels.keys())

    def logic(self, context):
        text = textwrap.dedent(context.sub(self.text))
        _level = self.level(context)
        if _level is None:
            _level = self._default_level
        level = self._levels.get(_level, logging.INFO)
        app_name = context.get('.app.name', None)
        if app_name is None:
            log = runtime_log
        else:
            log = logging.getLogger('moya.app.{}'.format(app_name))
        for line in text.splitlines():
            if line:
                log.log(level, line)


class LogDebug(Log):
    """See [tag]log[/tag]"""
    _default_level = "debug"

    class Help:
        synopsis = "write information to the log"


class LogInfo(Log):
    """See [tag]log[/tag]"""
    _default_level = "info"

    class Help:
        synopsis = "write information to the log"


class LogWarn(Log):
    """See [tag]log[/tag]"""
    _default_level = "warn"

    class Help:
        synopsis = "write information to the log"


class LogError(Log):
    """See [tag]log[/tag]"""
    _default_level = "error"

    class Help:
        synopsis = "write information to the log"


class LogFatal(Log):
    """See [tag]log[/tag]"""
    _default_level = "fatal"

    class Help:
        synopsis = "write information to the log"


class Enum(ElementBase):
    """Define and [i]enumeration[/i] object. An enumeration is a collection of text identifiers with an integer value. This tag should contain [tag]value[/tag] tags that define the values.

    It is generally preferably to use an enumeration over hard-coded numbers; it makes code easier to read and maintain.

    """
    start = Attribute("Starting ID if not specified in <enumvalue>", type="expression", default=1)

    class Help:
        synopsis = """map numbers on to identifiers"""
        example = """
        <enum libname="enum.jsonrpc.errors">
            <value id="1" label="not_logged_in" description="You must be logged in to do that" />
            <value label="invalid_score" description="Score must be -1, 0 or +1"/>
            <value label="unknown_link" description="Link object was not found"/>
        </enum>
        """

    def post_build(self, context):
        start = asint(self.start(context), 1)
        enum = ContextEnum(self.libid, start=start)
        self.archive.add_enum(enum)
        #startup_log.debug("%s created", enum)


class Value(ElementBase):
    """Defines a single value in an enumeration object. Should be contained within an [tag]enum[/tag]."""

    class Help:
        synopsis = """a value in an enumeration"""

    id = Attribute("Enumeration ID", type="integer", default=None)
    label = Attribute("Enumeration label", required=True)
    description = Attribute("Description of enumeration value", default='')
    group = Attribute("Group name", default='')

    def finalize(self, context):
        enum_parent = self.get_ancestor('enum')
        params = self.get_parameters(context)
        description = params.description
        if not description:
            description = context.sub(self.text)
        enum = self.archive.get_enum(enum_parent.libid)
        if description:
            description = description.strip()
        enum.add_value(params.label,
                       enum_id=params.id,
                       description=description,
                       group=params.group)


class GetEnum(DataSetter):
    """Get an enumeration object (see [tag]enum[/tag])."""

    class Help:
        synopsis = "get an enumeration"
        example = """
        <get-enum enum="sociallinks#enum.jsonrpc.errors" dst="errors" />
        <return value="errors.unknown_link" />

        """

    enum = Attribute("enumeration ref", type="elementref")

    def logic(self, context):
        enum = self.get_element(self.enum(context))
        self.set_context(context, dst, enum)


class GetTimezones(DataSetter):
    """Get a list of common timezones."""

    class Help:
        synopsis = """get common timezones"""
        example = """
        <get-timezones dst="timezones" />
        <echo>Timezones: ${commalist:timezones}</echo>

        """

    def logic(self, context):
        timezones = pytz.common_timezones[:]
        self.set_context(context, dst, timezones)


# class Signal(ElementBase):
#     """Define a [i]signal[/i]. A signal is a way of broadcasting to other parts of the project that a particular event has happened."""

#     name = Attribute("signal name", required=True)


class Handle(LogicElement):
    """
    Handles a [i]signal[/i]. A signal is a way of broadcasting to other parts of the project that a particular event has occurred.

    See [doc signals] for more information.

    """

    class Help:
        synopsis = """respond to a signal"""
        example = """

        <!-- Moya fires a number of signals itself, for various system events -->
        <handle signal="sys.startup">
            <log>This code executes on startup, prior to any requests</log>
        </handle>
        <!-- Handle a custom signal -->
        <handle signal="mordor.arrived">
            <log>${hobbit} has arrived in Mordor!</log>
        </handle>

        """

    signal = Attribute("Signal name to handle. Multiple names may be specified to handle more than one signal.""", type="commalist", required=True)
    sender = Attribute("Only handle the signal(s) if sent from this element.", default=None)

    def lib_finalize(self, context):
        sender, signals = self.get_parameters(context, 'sender', 'signal')
        if sender:
            sender = self.document.qualify_element_ref(sender, lib=self.lib)
            app, element = self.get_element(sender)
            sender = element.libid
        for signal in signals:
            self.archive.signals.add_handler(signal, self.libid, sender)


class Fire(LogicElement):
    """Fire (broadcast) a signal. Additional data may be provided to the signal handlers, by setting values in the [i]let map[/i]. Signals may be [i]handlers[/i] with the [tag]handle[/tag] tag.

    Moya will catch and log any exceptions raised by the signal handler(s).

    """
    signal = Attribute("Signal name, should be in a dotted notation. Names with no dots are reserved by Moya.", required=True)
    sender = Attribute("Optional element associated with the signal.", required=False, type="elementref", default=None)
    _from = Attribute("Application", type="application", required=False, default=None)

    class Help:
        synopsis = """fire a signal"""
        example = """
        <fire signal="mordor.arrived" let:hobbit="Frodo"/>
        """

    class Meta:
        trap_exceptions = True
        #is_call = True

    def logic(self, context):
        app = self.get_app(context)
        signal = self.signal(context)
        sender = self.sender(context)
        data = self.get_let_map(context)
        self.archive.fire(context,
                          signal,
                          app=app,
                          sender=sender,
                          data=data)
