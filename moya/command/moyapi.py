from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

import os
import io
import sys
import argparse
import getpass
import requests
import tempfile

from .. import settings
from .. import jsonrpc
from .. import package
from .. import versioning
from ..wsgi import WSGIApplication
from ..console import Console, Cell
from ..compat import text_type, raw_input
from ..command import downloader
from ..tools import get_moya_dir, is_moya_dir, nearest_word
from .. import build
from . import installer
from . import dependencies

import fs.utils
from fs.path import relativefrom, pathjoin
from fs.opener import fsopendir
from fs.tempfs import TempFS
from fs.zipfs import ZipFS


DEFAULT_CONF = "~/.moyapirc"
DEFAULT_HOST = "https://packages.moyaproject.com/jsonrpc/"


class CommandError(Exception):
    pass


class MoyaArgumentParser(argparse.ArgumentParser):
    """Some enhancements to argparse"""

    def _check_value(self, action, value):
        # converted value must be one of the choices (if specified)
        if action.choices is not None and value not in action.choices:

            nearest = nearest_word(value, action.choices)
            if nearest:
                msg = "invalid choice: '{}' (did you mean '{}')?\n".format(value, nearest)
            else:
                msg = "invalid choice: '{}'\n".format(value)
            self.print_usage()
            sys.stderr.write(msg)
            sys.exit(-1)


class MoyaPI(object):
    """\
Moya Package Index
==================

Find, install and manage Moya libraries
"""

    def __init__(self):
        self._rpc = None
        self._settings = None
        self.console = Console()

    @property
    def moyapirc_path(self):
        return os.path.expanduser(DEFAULT_CONF)

    def set_settings_defaults(self, settings):
        pass

    @property
    def settings(self):
        if self._settings is None:
            try:
                with io.open(os.path.expanduser(DEFAULT_CONF), 'rt') as f:
                    self._settings = settings.SettingsContainer.read_from_file(f)
            except IOError:
                self._settings = settings.SettingsContainer()
                self.set_settings_defaults(self._settings)
        return self._settings

    @property
    def user(self):
        username = self.settings.get('user', 'active', None)
        if not username:
            raise CommandError('no active user (run moya-pm auth or moya-pm user)')
        return username

    @property
    def auth_token(self):
        user = self.user
        token = self.settings.get('auth:{}'.format(user), 'token', None)
        if not token:
            raise CommandError('no auth token found (run moya-pm auth or moya-pm user)')
        return token

    def write_settings(self):
        with io.open(os.path.expanduser(DEFAULT_CONF), 'wt') as f:
            self.settings.export(f, "Written by moya-pm")

    @property
    def rpc(self):
        """Get the JSONRPC interface"""
        server_url = self.settings.get('server', 'url', DEFAULT_HOST)
        self.settings.set('server', 'url', server_url)
        if self._rpc is None:
            # Disable ssl cert verify, because it breaks on ubuntu
            self._rpc = jsonrpc.JSONRPC(server_url, ssl_verify=False)
        return self._rpc

    def call(self, method, **params):
        """Call an rpc method, exit if server is unreachable"""
        try:
            response = self.rpc.call(method, **params)
        except IOError as e:
            self.console.error("Unable to reach server ({})".format(e))
            sys.exit(-1)
        else:
            if isinstance(response, dict) and 'message' in response:
                for line in response['message'].splitlines():
                    if line.strip():
                        self.console('[server] ', fg="green")(line).nl()
            return response

    def get_argparse(self):
        parser = MoyaArgumentParser(prog="moya-pm",
                                    description=self.__doc__,
                                    formatter_class=argparse.RawDescriptionHelpFormatter,
                                    epilog="Need Help? http://moyaproject.com")

        parser.add_argument('-d', '--debug', dest="debug", action="store_true", help="enable debug information (show tracebacks)")

        subparsers = parser.add_subparsers(title="available sub-commands",
                                           dest="subcommand",
                                           help="sub-command help")

        # --- Auth subcommand ---
        auth_parser = subparsers.add_parser('auth',
                                            help="authorize with the server",
                                            description="Request authorization from the server (run once)")

        auth_parser.add_argument('-u', '--username', dest="username", default=None)
        auth_parser.add_argument('-p', '--password', dest="password", default=None)

        # --- User subcommand ---
        user_parser = subparsers.add_parser('user',
                                            help="switch active user",
                                            description="Switch between active user if you have multiple accounts")

        user_parser.add_argument(dest="user", default=None, nargs='?')

        # --- Register subcommand
        register_parser = subparsers.add_parser('register',
                                                help="register a package",
                                                description="Register a new package with the server")

        register_parser.add_argument(dest="location", help="library location")

        build_parser = subparsers.add_parser('build',
                                             help="build a package",
                                             description="Build a library")

        build_parser.add_argument(dest="location",
                                  metavar="PATH",
                                  help="Library location")
        build_parser.add_argument('-f', '--force', dest="force", action="store_true",
                                  help="Overwrite the package if it exists")
        build_parser.add_argument('-u', '--upload', dest="upload", action="store_true",
                                  help="Also upload package")
        build_parser.add_argument('--overwrite', dest="overwrite", action="store_true", default=False,
                                  help="Force over-writing of releases")

        upload_parser = subparsers.add_parser('upload',
                                              help="upload a package",
                                              description="Upload a package")

        upload_parser.add_argument(dest="location",
                                   help="Library location")
        upload_parser.add_argument('--version', dest="version", default=None, required=False,
                                   help="version to upload")
        upload_parser.add_argument('--overwrite', dest="overwrite", action="store_true", default=False,
                                   help="force over-writing of releases")
        upload_parser.add_argument('-d', '--docs', dest="docs", default=False, action="store_true",
                                   help="upload docs")

        list_parser = subparsers.add_parser('list',
                                            help="list package releases",
                                            description="List all releases for a package")

        list_parser.add_argument(dest='package', metavar="PACKAGE",
                                 help="Package to list (may also include version spec e.g. moya-pm list \"moya.packet>=1.1.0)\"")

        install_parser = subparsers.add_parser('install',
                                               help="install a package",
                                               description="Download and install a library")

        install_parser.add_argument(dest='package', metavar="PACKAGE",
                                    help="Package to installed (may include version spec e.g. moya.package>=1.0)")

        install_parser.add_argument("-l", '--location', dest="location", default=None, metavar="PATH",
                                    help="location of the Moya server code")
        install_parser.add_argument("-i", "--ini", dest="settings", default="settings.ini", metavar="SETTINGSPATH",
                                    help="path to project settings file")
        install_parser.add_argument('-d', "--download", dest="download", default=None, metavar="DIRECTORY",
                                    help="don't install package, just download package to DIRECTORY")
        install_parser.add_argument('-b', '--lib-dir', dest="output", default="external/", metavar="DIRECTORY",
                                    help="directory to install the library (relative to project root)")
        install_parser.add_argument('-f', '--force', dest="force", default=False, action="store_true",
                                    help="force overwrite of installed package")
        install_parser.add_argument('--upgrade', dest="upgrade", default=False, action="store_true",
                                    help="upgrade existing version")
        install_parser.add_argument('--mount', dest="mount", default=None,
                                    help="optional path to mount application")
        install_parser.add_argument('--app', dest="app", default=None,
                                    help="name of app to install")
        install_parser.add_argument('--no-add', dest="no_add", default=False, action="store_true",
                                    help="don't add to server.xml")
        install_parser.add_argument('--no-deps', dest="no_deps", default=False, action="store_true",
                                    help="don't install dependencies")

        return parser

    def run(self):
        parser = self.get_argparse()
        self.args = args = parser.parse_args(sys.argv[1:])

        if self.args.subcommand is None:
            parser.print_usage()
            return 1

        method_name = "run_" + args.subcommand.replace('_', '-')
        try:
            return getattr(self, method_name)() or 0
        except CommandError as e:
            self.console.error(text_type(e))
            return -1
        except jsonrpc.JSONRPCError as e:
            self.server_response(e.message, bold=True, fg="red")
            return e.code
        except Exception as e:
            self.console.error(text_type(e))
            if args.debug:
                raise
            return -1

    def server_response(self, text, **style):
        for line in text.splitlines():
            self.console('[server] ', **style)(line.lstrip()).nl()

    def run_auth(self):
        args = self.args
        username = args.username
        if username is None:
            username = getpass.getuser()
            if username:
                msg = "username ({}): ".format(username)
            else:
                msg = "username: "
            username = raw_input(msg) or username
            if not username:
                self.console.error('a username is required (see http://packages.moyaproject.com)')
                return
        password = args.password
        if password is None:
            password = getpass.getpass("{}'s password: ".format(username))
        auth_result = self.call('auth.get-token', username=username, password=password)

        auth_token = auth_result['token']
        self.settings.set('auth:{}'.format(username), 'token', auth_token)

        active_user = self.settings.get('user', 'active', None)
        if active_user is None:
            self.settings.set('user', 'active', username)

        self.write_settings()

        self.console.success("wrote auth token to '{}'".format(self.moyapirc_path))

    def run_user(self):
        args = self.args
        username = args.user
        if username is None:
            active_user = self.settings.get('user', 'active', None)
            if active_user is None:
                self.console.text('no active user')
            else:
                self.console.text("active username is '{}'".format(active_user))
        else:
            self.settings.set('user', 'active', username)
            self.write_settings()
            self.console.text("switched active user to '{}'".format(username))

    def run_register(self):
        args = self.args
        auth_token = self.auth_token

        path = os.path.abspath(os.path.join(args.location, 'lib.ini'))

        try:
            with io.open(path, 'rt') as f:
                lib_settings = settings.SettingsContainer.read_from_file(f)
        except IOError:
            self.console.error("unable to read library settings from '{}'".format(path))
            return -1

        def get(section, key, default=Ellipsis):
            try:
                return lib_settings.get(section, key, default=default)
            except:
                raise CommandError('key [{}]/{} was not found in lib.ini'.format(section, key))

        lib = dict(lib_settings['lib'])

        self.call('package.register', auth=auth_token, lib=lib)

    def run_build(self):
        args = self.args
        path = os.path.abspath(os.path.join(args.location, 'lib.ini'))
        try:
            with io.open(path, 'rt') as f:
                lib_settings = settings.SettingsContainer.read_from_file(f)
        except IOError:
            self.console.error("unable to read library settings from '{}'".format(path))
            return -1

        lib_name = lib_settings.get("lib", "name")
        lib_version = lib_settings.get("lib", "version")
        package_name = "{}-{}".format(lib_name, lib_version)
        package_filename = "{}.zip".format(package_name)

        exclude_wildcards = lib_settings.get_list("package", "exclude")
        exclude_wildcards.append('__moyapackage__/*')

        lib_fs = fsopendir(args.location)

        package_destination_fs = lib_fs.makeopendir('__moyapackage__')

        if not args.force and package_destination_fs.exists(package_filename):
            raise CommandError("package '{}' exists, use --force to overwrite".format(package_filename))

        package.make_package(lib_fs,
                             package_destination_fs,
                             package_filename,
                             exclude_wildcards,
                             auth_token=self.auth_token)

        output_path = package_destination_fs.getsyspath(package_filename)
        self.console.text("built '{}'".format(package_filename))
        if args.upload:
            upload_info = self.call('package.get-upload-info')
            upload_url = upload_info['url']

            self.upload(upload_url,
                        lib_name,
                        lib_version,
                        package_destination_fs,
                        package_filename,
                        overwrite=args.overwrite)

    def upload(self, url, package_name, version, build_fs, filename, overwrite=False):
        self.console("uploading '{}'...".format(filename)).nl()

        if not overwrite:
            try:
                self.call('package.get-download-info', package=package_name, version=version)

            except jsonrpc.JSONRPCError as e:
                if e.code != 7:
                    raise
            else:
                raise CommandError('''Upload failed because this release exists. It generally better to create a new release than overwrite an existing one.\n'''
                                   '''Use the --overwrite switch if you really want to do this.''')

        with build_fs.open(filename, 'rb') as package_file:
            files = [('file', (filename, package_file, 'application/octet-stream'))]
            data = {"auth": self.auth_token,
                    "package": package_name,
                    "version": version}

            username = self.settings.get('upload', 'username', None)
            password = self.settings.get('upload', 'password', None)
            if username and password:
                auth = (username, password)
            else:
                auth = None

            response = requests.post(url,
                                     verify=False,
                                     auth=auth,
                                     files=files,
                                     data=data,
                                     hooks={})

        if response.status_code != 200:
            raise CommandError("upload failed -- server returned {} response".format(response.status_code))

        message = response.headers.get(b'moya-upload-package-message', '').decode('utf-8')
        result = response.headers.get(b'moya-upload-package-result', '').decode('utf-8')

        if result == 'success':
            self.server_response(message, fg='green')
        else:
            raise CommandError(message)
        if result == "success":
            #self.console.success("package was uploaded")
            pass
        else:
            self.console.error("upload failed")

    def run_upload(self):
        args = self.args

        path = os.path.abspath(os.path.join(args.location, 'lib.ini'))
        try:
            with io.open(path, 'rt') as f:
                lib_settings = settings.SettingsContainer.read_from_file(f)
        except IOError:
            self.console.error("unable to read library settings from '{}'".format(path))
            return -1

        lib_name = lib_settings.get("lib", "name")
        lib_version = args.version or lib_settings.get("lib", "version")

        if args.docs:
            return self.upload_docs(lib_name, lib_version)

        package_name = "{}-{}".format(lib_name, lib_version)
        package_filename = "{}.zip".format(package_name)

        upload_info = self.call('package.get-upload-info')
        upload_url = upload_info['url']

        lib_fs = fsopendir(args.location)
        package_destination_fs = lib_fs.makeopendir('__moyapackage__')

        if not package_destination_fs.exists(package_filename):
            raise CommandError("package '{}' does not exist, run 'moya-pm build'".format(package_filename))

        self.upload(upload_url,
                    lib_name,
                    lib_version,
                    package_destination_fs,
                    package_filename,
                    overwrite=args.overwrite)

    def upload_docs(self, lib_name, lib_version):
        args = self.args

        archive, lib = build.build_lib(args.location, ignore_errors=True)
        #archive.finalize()
        lib_name = lib.long_name

        #namespaces = list(archive.known_namespaces)
        from ..docgen.extracter import Extracter

        extract_fs = TempFS('moyadoc-{}'.format(lib_name))

        extracter = Extracter(archive, extract_fs)
        extracter.extract_lib(lib_name)

        _fh, temp_filename = tempfile.mkstemp('moyadocs')
        #temp_filename = "docs.zip"

        with ZipFS(temp_filename, 'w') as docs_zip_fs:
            fs.utils.copydir(extract_fs, docs_zip_fs)

        package_filename = "{}-{}.docs.zip".format(lib_name, lib_version)

        upload_info = self.call('package.get-upload-info')
        docs_url = upload_info['docs_url']

        self.console("uploading '{}'...".format(package_filename)).nl()

        with io.open(temp_filename, 'rb') as package_file:
            files = [('file', (package_filename, package_file, 'application/octet-stream'))]
            data = {"auth": self.auth_token,
                    "package": lib_name,
                    "version": lib_version}

            response = requests.post(docs_url,
                                     verify=False,
                                     files=files,
                                     data=data,
                                     hooks={})

        if response.status_code != 200:
            raise CommandError("upload failed -- server returned {} response".format(response.status_code))

        message = response.headers.get(b'moya-upload-package-message', '').decode('utf-8')
        result = response.headers.get(b'moya-upload-package-result', '').decode('utf-8')

        if result == 'success':
            self.server_response(message, fg="green")
        else:
            raise CommandError('upload error ({})'.format(message))
        if result == "success":
            #self.console.success("package was uploaded")
            pass
        else:
            self.console.error("upload failed")

    def run_list(self):
        args = self.args
        package = args.package
        version_spec = versioning.VersionSpec(package)

        releases = self.call('package.list-releases', package=version_spec.name)['releases']

        releases.sort(key=lambda r: versioning.Version(r['version']))
        table = []
        for release in releases:
            if version_spec.comparisons and release['version'] not in version_spec:
                continue
            table.append([Cell(release['version'], bold=True, fg="magenta"), release['notes']])

        self.console.table(table, header_row=['version', 'release notes'])

    @property
    def location(self):
        _location = getattr(self, '_location', None)
        if _location is not None:
            return _location
        location = self.args.location
        if location is None:
            location = './'
        if location and '://' in location:
            return location
        try:
            location = get_moya_dir(location) + '/'
        except ValueError:
            raise CommandError("Moya project directory not found, run this command from a project directory or specify --location")
        if not is_moya_dir(location):
            raise CommandError("Location is not a moya project (no 'moya' file found)")
        self._location = location
        return location

    def run_install(self):
        args = self.args
        console = self.console
        installed = []
        install_package = args.package

        install_select = package_select = self.call('package.select', package=install_package)
        install_notes = package_select['notes']

        if package_select['version'] is None:
            raise CommandError("no install candidate for '{}', run 'moya-pm list' to see available packages".format(install_package))

        package_name = package_select['name']
        install_version = versioning.Version(package_select['version'])

        filename = package_select['md5']
        download_url = package_select['download']
        package_filename = download_url.rsplit('/', 1)[-1]

        libs = []
        output_fs = fsopendir(args.output)
        force = args.force

        installed_libs = {}

        archive = None
        if not args.download:
            try:
                application = WSGIApplication(self.location, args.settings, disable_autoreload=True)
                archive = application.archive
                if archive is None:
                    console.text('unable to load project, use the --force switch to force installation')
                    return -1
            except Exception as e:
                if not args.force:
                    console.exception(e)
                    console.text('unable to load project, use the --force switch to force installation')
                    return -1
            else:
                libs = [(lib.long_name, lib.version, lib.install_location)
                        for lib in archive.libs.values() if lib.long_name == package_name]

                installed_libs = archive.libs.copy()

                if not force:
                    for name, version, location in libs:
                        if name == package_name:
                            if version > install_version:
                                if not args.force:
                                    raise CommandError("a newer version ({}) is already installed, use --force to force installation".format(version))
                            elif install_version == version:
                                if not args.force:
                                    raise CommandError("version {} is already installed, use --force to force installation".format(version))
                            else:
                                if not args.upgrade:
                                    raise CommandError("an older version ({}) is installed, use --upgrade to force upgrade".format(version))
                            force = True

        username = self.settings.get('upload', 'username', None)
        password = self.settings.get('upload', 'password', None)
        if username and password:
            auth = (username, password)
        else:
            auth = None

        install_app = args.app or package_name.split('.')[-1]
        packages = dependencies.gather_dependencies(self.rpc,
                                                    install_app,
                                                    args.mount,
                                                    install_package,
                                                    console,
                                                    no_deps=args.no_deps)

        if not args.no_add:
            for package_name, (app_name, mount, package_select) in packages.items():
                if package_select['version'] is None:
                    raise CommandError("no install candidate for required package '{}', run 'moya-pm list {}' to see available packages".format(package_name, package_name))

        download_temp_fs = TempFS()
        for package_name, (app_name, mount, package_select) in packages.items():

            package_name = package_select['name']
            install_version = versioning.Version(package_select['version'])

            filename = "{}-{}.{}".format(package_name, install_version, package_select['md5'])
            download_url = package_select['download']
            package_filename = download_url.rsplit('/', 1)[-1]

            with download_temp_fs.open(filename, 'wb') as package_file:
                checksum = downloader.download(download_url,
                                               package_file,
                                               console=console,
                                               auth=auth,
                                               verify_ssl=False,
                                               msg="requesting {name}=={version}".format(**package_select))
                if checksum != package_select['md5']:
                    raise CommandError("md5 checksum of download doesn't match server! download={}, server={}".format(checksum, package_select['md5']))

            if args.download:
                with fsopendir(args.download) as dest_fs:
                    fs.utils.copyfile(download_temp_fs, filename, dest_fs, package_filename)

        if args.download:
            return 0

        changed_server_xml = False
        for package_name, (app_name, mount, package_select) in packages.items():

            package_name = package_select['name']
            install_version = versioning.Version(package_select['version'])

            filename = "{}-{}.{}".format(package_name, install_version, package_select['md5'])
            download_url = package_select['download']
            package_filename = download_url.rsplit('/', 1)[-1]

            install_location = relativefrom(self.location, pathjoin(self.location, args.output, package_select['name']))
            package_select['location'] = install_location

            with download_temp_fs.open(filename, 'rb') as package_file:
                with ZipFS(package_file, 'r') as package_fs:
                    with output_fs.makeopendir(package_select['name']) as lib_fs:
                        #if not lib_fs.isdirempty('/') and not force:
                        #    raise CommandError("install directory is not empty, use --force to erase and overwrite")
                        fs.utils.remove_all(lib_fs, '/')
                        fs.utils.copydir(package_fs, lib_fs)
                        installed.append((package_select, mount))

            if not args.no_add and archive:
                server_xml = archive.cfg.get('project', 'startup')
                changed_server_xml =\
                    installer.install(project_path=self.location,
                                      server_xml_location=archive.cfg.get('project', 'location'),
                                      server_xml=server_xml,
                                      server_name=application.server_ref,
                                      lib_path=install_location,
                                      lib_name=package_name,
                                      app_name=app_name,
                                      mount=mount)

        table = []
        for _package, mount in installed:
            table.append([Cell("{name}=={version}".format(**_package), fg="magenta", bold=True),
                          Cell(_package['location'], fg="blue", bold=True),
                          Cell(mount or '', fg="cyan", bold=True)])

        if table:
            console.table(table, ['package', 'location', 'mount'])

        if install_notes:
            console.table([[install_notes]], ['{} v{} release notes'.format(install_select['name'], install_select['version'])])

        if changed_server_xml:
            console.text("moya-pm modified '{}' -- please check changes".format(server_xml), fg="green", bold="yes")



def main():
    return MoyaPI().run()
