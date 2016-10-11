from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

import fs.copy
from fs.opener import open_fs
from fs import walk

from ...command import SubCommand
from ...console import Cell
from ...command.sub import templatebuilder
from ...compat import text_type, raw_input

import sys
try:
    import readline
except ImportError:
    pass

import random


def make_secret(size=64, allowed_chars='0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ!#$%&()*+,-./:;<=>?@[]^_`{|}~'):
    """make a secret key"""
    try:
        choice = random.SystemRandom().choice
    except:
        choice = random.choice
    return ''.join(choice(allowed_chars) for _ in range(size))


def make_name(*names):
    names = [
        ''.join(c for c in name.lower() if c.isalpha() or c.isdigit())
        for name in names
    ]
    return '.'.join(names)


def copy_new(src, dst):
    """Copy files from src fs to dst fst only if they don't exist on dst"""
    fs.copy.copy_structure(src, dst)
    copied_files = []
    for path in walk.walk_files(src):
        if not dst.exists(path):
            fs.copy.copy_file(src, path, dst, path)
            copied_files.append(path)
    return copied_files


class Question(object):
    text = """Which pill do you take?"""
    alert = None
    extra = None
    responses = None
    examples = None
    required = True
    accept_defaults = False

    @classmethod
    def ask(cls, console, default=None):
        question_text = cls.text + ' '
        while True:
            if cls.alert:
                console.wraptext(cls.alert, fg="red", bold=True)

            console(question_text, bold=True)
            if default is not None:
                console.text(" {} ".format(default or '<leave blank>'), fg="blue", bold=True)
            else:
                console.nl()
            if not (cls.accept_defaults and default is not None):
                if cls.extra:
                    console.table([[cls.extra]])
                if cls.examples:
                    console("e.g. ", fg="blue", bold=True)(cls.examples[0], fg="green").nl()
                    for e in cls.examples[1:]:
                        console("     ")(e, fg="green").nl()
            if cls.accept_defaults and default is not None:
                response = cls.process_input(default)
                if not isinstance(response, text_type):
                    response = response.decode(sys.getdefaultencoding(), 'replace')
                break

            try:
                response = raw_input()
            except KeyboardInterrupt:
                console.nl().text("\rCanceled", bold=True, fg="red")
                raise
            if not isinstance(response, text_type):
                response = response.decode(sys.getdefaultencoding(), 'replace')

            response = cls.process_input(response)
            if not response and default is not None:
                response = default

            if cls.required and not response.strip():
                console.text("This question requires an answer to continue", fg="red")
                continue

            if cls.responses is not None and not (response in cls.responses):
                console.text("Not a valid response, please try again", fg="red")
                continue

            break
        return cls.process_response(response)

    @classmethod
    def process_input(cls, text):
        return text

    @classmethod
    def process_response(cls, response):
        return response


class YesNoQuestion(Question):
    responses = ["y", "yes", "n", "no"]

    @classmethod
    def process_input(cls, response):
        return response.strip().lower()

    @classmethod
    def process_response(cls, response):
        return response.lower() in ("y", "yes")


class Name(Question):
    text = """What is your name?"""


class Email(Question):
    text = """What is your email address?"""


class Organization(Question):
    text = """What is your organization?"""
    extra = """This may be your employer, organization or your own name"""


class URL(Question):
    text = """What is your homepage URL?"""
    required = False


class DoMount(YesNoQuestion):
    text = """Do you want to mount this library?"""


class ProjectTitle(Question):
    text = """What is the title of your project?"""


class ProjectLongName(Question):
    text = """What is the 'long name' of your project?"""
    extra = """Moya 'long names' are globally unique identifiers. A long name consists of two or more words separated by dots. The first word should be unique to you (i.e. your name or organization), subsequent words should identify the project."""
    examples = ["bob.blog",
                "acmesoftware.kitchen.sink"]


class ProjectDirName(Question):
    text = """Where should Moya write the project files?"""


class Preview(YesNoQuestion):
    text = """Would you like to preview the files that will be generated?"""


class ContinueWrite(YesNoQuestion):
    text = """Write project files?"""


class DirNotEmpty(Question):
    text = """The destination directory is not empty! If you continue, files may be overwritten and data lost."""
    extra = """'cancel' to exit without writing files\n'overwrite' to overwrite any existing files\n'new' to write only new files."""
    responses = ["overwrite", "cancel", "new"]


class Database(YesNoQuestion):
    text = """Do you want database support?"""


class Auth(YesNoQuestion):
    text = """Enable Moya auth support?"""
    extra = """Enable if you want to support users with authentication and permissions (a requirement for most dynamic sites)."""


class Signup(YesNoQuestion):
    text = """Enable Moya signup support?"""
    enable = """Enable to allow users to create accounts."""


class JSONRPC(YesNoQuestion):
    text = """Enable JSON RPC support for your site?"""
    extra = """Enable to provide an API you can use to expose code and data (see http://json-rpc.org/)."""


class Pages(YesNoQuestion):
    text = """Enable pages application?"""
    extra = """moya.pages is a simple content management system useful for about/contact pages etc."""


class Blog(YesNoQuestion):
    text = """Enable blog application?"""
    extra = """moya.blog is a simple, but feature complete, blog system."""


class Feedback(YesNoQuestion):
    text = """Enable feedback application?"""
    extra = """moya.feedback provides a feedback form visitors can use to email you."""


class LibraryTitle(Question):
    text = """What is the title of your library?"""


class LibraryURL(Question):
    text = """What is the URL of your library?"""
    extra = """It's a good idea to provide a URL for your library that contains more information about it. Leave this blank if you want to fill it in later."""
    examples = ["http://example.org/moya/awesomelib.html"]
    required = False


class LibraryLongName(Question):
    text = """What is the 'long name' of your library?"""
    extra = """Moya 'long names' are globally unique identifiers. A long name consistst of two or more words separated by dots. The first word should be unique to you (i.e. your name or organization), subsequent words should identify the library."""
    examples = ["bob.blog",
                "acmesoftware.kitchen.sink"]


class LibraryNamespace(Question):
    text = """What xml namespace do you want to use for your library?"""
    extra = """The namespace will be used for any tags you define. You can leave this blank if you won't be creating any tags, or if you prefer to enter this later."""
    examples = ["http://acmesoftware.com/namespaces/libs",
                "http://example.org/blog"]
    required = False


class Mount(Question):
    text = """What URL would you like to mount the new library on?"""
    examples = ["/blog/",
                "/shop/beetles/"]
    required = False


class AppName(Question):
    text = """What should the application be named?"""
    extra = """A mounted application requires a 'short name', which should be a single word, no space or dots."""
    examples = ["myblog",
                "beetlesshop"]
    required = False


class Start(SubCommand):
    """Start a Moya library or project"""
    help = "command line wizard to create a project or library"

    def add_arguments(Self, parser):

        parser.add_argument("--templatize", dest="templatize", metavar="PATH",
                            help="make a filesystem template (used internally, not required for general use)")

        subparser = parser.add_subparsers(title="start sub-command",
                                          dest="type",
                                          help="what to create")

        def add_common(parser):
            parser.add_argument("-l", dest="project_location", default='./', metavar="PATH",
                                help="location of the Moya server code")
            parser.add_argument("-i", "--ini", dest="settings", default=None, metavar="SETTINGSPATH",
                                help="path to project settings file")
            parser.add_argument("-o", dest="location", metavar="PATH", default=None,
                                help="""location of new project / library""")
            parser.add_argument("-a", "--accept-defaults", dest="acceptdefaults", action="store_true", default=False,
                                help="automatically accept all defaults")
            parser.add_argument('-t', '--title', dest="title",
                                help="project / library title")
            parser.add_argument('-f', '--force', dest="force", action="store_true", default=False,
                                help="force overwriting of files if destination directory is not empty")
            parser.add_argument('-n', '--new', dest="new", action="store_true", default=False,
                                help="write new files only")
            return parser

        add_common(subparser.add_parser('project',
                                        help="start a new Moya project",
                                        description="Start a new Moya project"))

        parser = add_common(subparser.add_parser('library',
                                                 help="start a new library in a Moya project",
                                                 description="Start a new library in a Moya project"))
        parser.add_argument('--mount', dest="mount", default=None, metavar="URL PATH",
                            help="URL where the library should be mounted")
        parser.add_argument('--longname', dest="longname", default=None, metavar="LONG NAME",
                            help="Name of the installed library")
        parser.add_argument('--name', dest="name", default=None, metavar="APPLICATION NAME",
                            help="Application name if the lib is mounted")
        # parser.add_argument(dest="type", metavar="'PROJECT' or 'LIBRARY'",
        #                         help="what to create")
        return parser

    def run(self):
        args = self.args

        Question.accept_defaults = args.acceptdefaults

        if args.templatize:
            return self.templatize(args.templatize)

        if args.type.lower() == "project":
            return self.start_project()

        elif args.type.lower() == "library":
            return self.start_library()

        raise ValueError("Type should be either 'project' or 'library'")

    def templatize(self, path):
        from fs.opener import open_fs
        from fs.path import splitext, split
        fs = open_fs(path)
        text_ext = ['', '.py', '.ini', '.xml', '.html', '.txt', '.json']
        bin_ext = ['.png', '.jpg', '.ico', '.gif']

        def check_path(path):
            dirname, filename = split(path)
            return filename not in [".svn", ".hg"]

        for path in walk.walk_files(fs):
            if check_path(path):
                continue
            _, ext = splitext(path)
            ext = ext.lower()
            if ext in text_ext:
                print('@TEXT {}'.format(path))
                for line in fs.open(path, 'rt'):
                    print(line.rstrip())
            elif ext in bin_ext:
                print('@BIN {}'.format(path))
                with fs.open(path, 'rb') as f:
                    chunk = f.read(64)
                    while chunk:
                        print(''.join('%02x' % ord(b) for b in chunk))
                        chunk = f.read(64)

    def get_timezone(self):
        # get the system timezone
        # TODO: investigate a more cross platform way of doing this
        try:
            with open('/etc/timezone') as f:
                timezone = f.read()
        except IOError:
            timezone = 'UTC'
        return timezone

    def start_project(self):
        console = self.console

        if not self.args.acceptdefaults:
            console.table([[Cell("Moya Project Wizard", bold=True, fg="green", center=True)],
                          ["""This will ask you a few questions, then create a new Moya project based on your answers.

Default values are shown in blue (hit return to accept defaults). Some defaults may be taken from your ".moyarc" file, if it exists."""]])

        author = self.get_author_details()
        project = {}
        project["title"] = ProjectTitle.ask(console, default=self.args.title)
        longname = make_name(author["organization"], project["title"])
        project["database"] = Database.ask(console, default='y')
        if project["database"]:
            project["auth"] = Auth.ask(console, default='y')
            project['signup'] = Signup.ask(console, default='y')
            project["pages"] = Pages.ask(console, default='y')
            project["blog"] = Blog.ask(console, default='y')
        project["feedback"] = Feedback.ask(console, default='y')
        project["comments"] = project.get("blog", False) or project.get("pages", False)
        project["wysihtml5"] = project.get("blog", False) or project.get("pages", False)
        project['jsonrpc'] = JSONRPC.ask(console, default='y')

        dirname = longname.split('.', 1)[-1].replace('.', '_')
        dirname = ProjectDirName.ask(console, default="./" + dirname)

        data = {
            "author": author,
            "project": project,
            "timezone": self.get_timezone(),
            "secret": make_secret()
        }

        from ...command.sub import project_template
        memfs = open_fs('mem://')
        templatebuilder.compile_fs_template(memfs,
                                            project_template.template,
                                            data=data)

        dest_fs = open_fs(self.args.location or dirname, create=True, writeable=True)
        continue_overwrite = 'overwrite'
        if not dest_fs.isempty('.'):
            if self.args.force:
                continue_overwrite = 'overwrite'
            elif self.args.new:
                continue_overwrite = 'new'
            else:
                continue_overwrite = DirNotEmpty.ask(console, default="cancel")

        if continue_overwrite == 'overwrite':
            fs.copy.copy_dir(memfs, '/', dest_fs, '/')
            console.table([[Cell("Project files written successfully!", fg="green", bold=True, center=True)],
                          ["""See readme.txt in the project directory for the next steps.\n\nBrowse to http://moyaproject.com/gettingstarted/ if you need further help."""]])
            return 0
        elif continue_overwrite == 'new':
            files_copied = copy_new(memfs, dest_fs)
            table = [[
                     Cell("{} new file(s) written".format(len(files_copied)), fg="green", bold=True, center=True),
                     ]]
            for path in files_copied:
                table.append([Cell(dest_fs.desc(path), bold=True, fg="black")])
            console.table(table)
            return 0

        console.text("No project files written.", fg="red", bold=True).nl()
        return -1

    def start_library(self):
        console = self.console

        from ...tools import get_moya_dir
        from os.path import join, abspath
        project_path = None
        if self.args.location is not None:
            library_path = self.args.location
        else:
            try:
                project_path = get_moya_dir(self.args.project_location)
            except:
                console.error("Please run 'moya start library' inside your project directory, or specifiy the -o switch")
                return False
            library_path = abspath(join(project_path, './local/'))

        cfg = None
        if not self.args.location and project_path:
            from ... import build
            cfg = build.read_config(project_path, self.get_settings())

        if not self.args.acceptdefaults:
            console.table([[Cell("Moya Library Wizard", bold=True, fg="green", center=True)],
                          ["""This will ask you a few questions, then create a new library in your Moya project based on your answers.

Default values are shown in grey (simply hit return to accept defaults). Some defaults may be taken from your ".moyarc" file, if it exists.
"""]])
        author = self.get_author_details()
        library = {}
        library["title"] = LibraryTitle.ask(console, default=self.args.title)
        longname = self.args.longname or make_name(author["organization"], library["title"])
        longname = library["longname"] = LibraryLongName.ask(console, default=longname)
        library["url"] = LibraryURL.ask(console, default="")
        library["namespace"] = LibraryNamespace.ask(console, default="")
        mount = None
        appname = None

        do_mount = DoMount.ask(console, default="yes")
        if do_mount:
            mount = Mount.ask(console, default=self.args.mount or "/{}/".format(make_name(library["title"])))
            appname = AppName.ask(console, default=self.args.name or make_name(library["title"]))

        data = dict(author=author,
                    library=library,
                    timezone=self.get_timezone())

        actions = []

        from ...command.sub import library_template

        memfs = open_fs('mem://')
        templatebuilder.compile_fs_template(memfs,
                                            library_template.template,
                                            data=data)
        dest_fs = open_fs(join(library_path, library["longname"]), create=True, writeable=True)

        continue_overwrite = 'overwrite'
        if not dest_fs.isempty('/'):
            if self.args.force:
                continue_overwrite = 'overwrite'
            elif self.args.new:
                continue_overwrite = 'new'
            else:
                continue_overwrite = DirNotEmpty.ask(console, default="cancel")

        if continue_overwrite != 'cancel':
            if continue_overwrite == 'overwrite':
                fs.copy.copy_dir(memfs, '/', dest_fs, '/')
                actions.append("Written library files to {}".format(dest_fs.getsyspath('.')))
            elif continue_overwrite == 'new':
                files_copied = copy_new(memfs, dest_fs)
                table = [[
                         Cell("{} new file(s) written".format(len(files_copied)), fg="green", bold=True, center=True),
                         ]]
                for path in files_copied:
                    table.append([Cell(dest_fs.desc(path), bold=True, fg="black")])
                console.table(table)
                return 0

            if cfg:
                project_cfg = cfg['project']
                location = project_cfg['location']
                server_name = "main"

                if location:
                    with open_fs(project_path) as project_fs:
                        with project_fs.opendir(location) as server_fs:
                            from lxml.etree import fromstring, ElementTree, parse
                            from lxml.etree import XML, Comment
                            server_xml_path = server_fs.getsyspath(project_cfg['startup'])
                            root = parse(server_xml_path)
                            import_tag = XML('<import location="./local/{longname}" />\n\n'.format(**library))
                            import_tag.tail = "\n"
                            install_tag = None

                            if mount:
                                tag = '<install name="{appname}" lib="{longname}" mount="{mount}" />'
                            else:
                                tag = '<install name="{appname}" lib="{longname}" />'
                            install_tag = XML(tag.format(appname=appname,
                                                         longname=longname,
                                                         mount=mount))
                            install_tag.tail = "\n\n"

                            def has_child(node, tag, **attribs):
                                for el in node.findall(tag):
                                    if all(el.get(k, None) == v for k, v in attribs.items()):
                                        return True
                                return False

                            for server in root.findall("{{http://moyaproject.com}}server[@docname='{}']".format(server_name)):
                                add_import_tag = not has_child(server, "{http://moyaproject.com}import", location="./local/{}".format(longname))
                                add_install_tag = not has_child(server, "{http://moyaproject.com}install", lib=longname) and install_tag is not None

                                if add_import_tag or add_install_tag:
                                    comment = Comment("Added by 'moya start library'")
                                    comment.tail = "\n"
                                    server.append(comment)
                                if add_import_tag:
                                    server.append(import_tag)
                                    actions.append("Added <import> tag")
                                if add_install_tag:
                                    server.append(install_tag)
                                    actions.append("Added <install> tag")
                                    if mount:
                                        actions.append("Mounted application on {}".format(mount))

                            root.write(server_xml_path)

            table = [[Cell("Library files written successfully!", fg="green", bold=True, center=True)]]

            actions_text = "\n".join(" * " + action for action in actions)
            table.append([Cell(actions_text, fg="blue", bold=True)])
            table.append(["""A new library has been added to the project, containing some simple example functionality.\nSee http://moyaproject.com/docs/creatinglibraries/ for more information."""])
            console.table(table)

            return 0

        console.text("No project files written.", fg="red", bold=True).nl()
        return -1

    def get_author_details(self):
        console = self.console
        moyarc = self.moyarc
        author = {}
        author["name"] = Name.ask(console, default=moyarc.get('author', 'name', None))
        author["email"] = Email.ask(console, default=moyarc.get('author', 'email', None))
        author["url"] = URL.ask(console, default=moyarc.get('author', 'url', None))
        author["organization"] = Organization.ask(console, default=moyarc.get('author', 'organization', None))
        return author
