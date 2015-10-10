from __future__ import unicode_literals, print_function

from ..elements.elementbase import ElementBase, Attribute
from .. import namespaces
from ..compat import text_type, implements_to_string
from ..errors import ElementError

from operator import itemgetter
import io


@implements_to_string
class FileReader(object):
    def __init__(self, element, path):
        self.element = element
        self.path = path

    def __call__(self, path):
        self.path = path

    def __str__(self):
        return "<filereader '{}'>".format(self.path)

    def __moyarepr__(self, context):
        return "<filereader '{}'>".format(self.path)

    @property
    def binary(self):
        try:
            with io.open(self.path, 'rb') as f:
                return f.read()
        except IOError:
            raise ElementError('unable to read "{}"'.format(self.path), element=self.element)

    @property
    def text(self):
        try:
            with io.open(self.path, 'rt') as f:
                return f.read()
        except IOError:
            raise ElementError('unable to read "{}"'.format(self.path), element=self.element)


class Command(ElementBase):
    """
    Defines a command accessible from the command line. To invoke a command enter its full app name after 'moya'. For example:

    [code]$ moya testapp#cmd.hello World
Hello, World!
    [/code]

    You can also get a list of available commands for an application, by supplying the app name followed by #. For example:

    [code]$ moya testapp#[/code]

    See [doc commands] for more information.

    """

    class Help:
        synopsis = """define a command"""
        example = """
        <command libname="cmd.hello" sypopsis="Greet someone on the commandline">
            <signature>
                <arg name="who" help="Who you want to greet">
            </signature>
            <echo>Hello, ${who}!</echo>
        </command>
        """

    _element_class = "command"
    synopsis = Attribute("Command synopsis, displayed when you list commands")
    init = Attribute("Run this command as part of the init process?", type="boolean", default=False)
    priority = Attribute("Priority for init process (higher piority commands will be run first)", type="integer", default=0)

    class Meta:
        logic_skip = True

    def document_finalize(self, context):
        self._synopsis = self.synopsis(context)
        self._doc = None
        self._init = self.init(context)
        self._priority = self.priority(context)
        for doc in self.get_children(element_type=(namespaces.default, 'doc')):
            self._doc = doc.text
        self._signature = _signature = {'options': [],
                                        'arguments': [],
                                        'switches': []}
        for signature in self.children(element_type=(namespaces.default, 'signature')):

            for element in signature.children(element_type='option'):
                params = element.get_all_parameters(context)
                _signature['options'].append(params)

            for element in signature.children(element_type='arg'):
                params = element.get_all_parameters(context)
                _signature['arguments'].append(params)

            for element in signature.children(element_type='switch'):
                params = element.get_all_parameters(context)
                _signature['switch'].append(params)

        _signature['options'].sort(key=itemgetter('name'))
        _signature['arguments'].sort(key=itemgetter('name'))
        _signature['switches'].sort(key=itemgetter('name'))
        _signature['alloptions'] = _signature['options'] + _signature['switches']
        _signature['alloptions'].sort(key=itemgetter('name'))

    _types = {
        "string": lambda el: text_type,
        "int": lambda el: int,
        "integer": lambda el: int,
        "float": lambda el: float,
        "file": lambda el: lambda p: FileReader(el, p)
    }

    def update_parser(self, parser, context):

        for signature in self.children(element_type='signature'):
            for element in signature.children(element_type='option'):
                params = element.get_parameters(context)
                if params.action:
                    parser.add_argument('--' + params.name,
                                        dest=params.name,
                                        default=params.default,
                                        help=params.help,
                                        action=params.action)
                else:
                    parser.add_argument('--' + params.name,
                                        dest=params.name,
                                        default=params.default,
                                        help=params.help,
                                        type=self._types[params.type](self))
            for element in signature.children(element_type='arg'):
                params = element.get_parameters(context)
                parser.add_argument(dest=params.name,
                                    nargs=params.nargs,
                                    help=params.help,
                                    metavar=params.metavar,
                                    type=self._types[params.type](self))
            # for element in signature.children(element_type='switch'):
            #     params = element.get_parameters(context)
            #     parser.add_argument('--' + params.name,
            #                         dest=params.name,
            #                         help=params.help,
            #                         action="store_true",
            #                         default=False)


class Arg(ElementBase):
    """Defines an argument for a [link commands]command[/link]. An [tag]arg[/tag] tag must appear within the [tag]signature[/tag] tag for a command."""

    class Help:
        synopsis = """add a positional argument to a command"""
        example = """
        <!-- Should appear within a <signature> tag -->
        <arg name="who" help="Who you want to greet">
        """

    _element_class = "command"
    name = Attribute("Argument name (the variable when the command is execute)")
    nargs = Attribute("Number of arguments to be consumed", default=None)
    help = Attribute("Argument help text", default=None)
    metavar = Attribute("Argument metavar (shown in the help)")
    type = Attribute("Type of argument", choices=["string", 'integer', 'float', 'file'], default="string")

    class Meta:
        logic_skip = True


class Option(ElementBase):
    """Defines an [i]option[/i] for a [tag]command[/tag]. Options may be added to the command line when a command is invoked. The following is an example of how an option is used:

    [code]$ moya testapp#cmd.optiontest --hobbit="bilbo"[/code]

    An [tag]option[/tag] tag must appear within a [tag]signature[/tag] tag.

    """

    class Help:
        synopsis = """Add an option to a command"""
        example = """
        <option name="hobbit" metavar="HOBBIT NAME" help="Your favorite hobbit" />
        """

    _element_class = "command"
    name = Attribute("Argument name")
    nargs = Attribute("Number of arguments", default='?')
    help = Attribute("Argument help text")
    default = Attribute("Default", default=None)
    metavar = Attribute("Argument metavar")
    action = Attribute("Action", default=None)
    type = Attribute("Type of argument", choices=["string", 'integer', 'float', 'file'], default="string")

    class Meta:
        logic_skip = True
