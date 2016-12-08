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
from ..tools import get_moya_dir, is_moya_dir, nearest_word, decode_utf8_bytes
from .. import build
from . import installer
from . import dependencies

import fs.copy
from fs.path import relativefrom, join
from fs.opener import open_fs
from fs.tempfs import TempFS
from fs.zipfs import ZipFS
from fs.osfs import OSFS


DEFAULT_CONF = "~/.moyapirc"
DEFAULT_HOST = "https://packages.moyaproject.com/jsonrpc/"


"""
    <enum libname="enum.jsonrpc.errors">
        <value id="0" name="ok">No error (not used)</value>
        <value id="1" name="no_user">No such user on the system</value>
        <value name="password_failed">Password does not match</value>
        <value name="auth_failed">Auth token was not valid</value>
        <value name="no_access">You don't have access to this resource</value>
        <value name="no_organization">No such organization</value>
        <value name="no_package">No such package</value>
        <value name="no_release">No such package version</value>
        <value name="lib_invalid">Library data is invalid</value>
        <value name="organization_create_error">Unable to get/create organization</value>
        <value name="version_invalid">The version spec was not in the correct format</value>
    </enum>
"""


class MOYAPI_ERRORS:
    ok = 0
    no_user = 1
    password_failed = 2
    auth_failed = 3
    no_access = 4
    no_organization = 5
    no_package = 6
    no_release = 7
    lib_invalid = 8
    organization_create_error = 9
    version_invalid = 10


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

        install_parser.add_argument(dest='packages', metavar="PACKAGES", nargs="*",
                                    help="Package to installed (may include version spec e.g. moya.package>=1.0)")

        install_parser.add_argument("-l", '--location', dest="location", default=None, metavar="PATH",
                                    help="location of the Moya server code")
        install_parser.add_argument("-i", "--ini", dest="settings", default="settings.ini", metavar="SETTINGSPATH",
                                    help="path to project settings file")
        install_parser.add_argument("-s", "--server", dest="server", default="main", metavar="SERVERREF",
                                    help="server element to use")
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

        lib_fs = open_fs(args.location)

        package_destination_fs = lib_fs.makedir('__moyapackage__', recreate=True)

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

        message = decode_utf8_bytes(response.headers.get('moya-upload-package-message', ''))
        result = decode_utf8_bytes(response.headers.get('moya-upload-package-result', ''))

        if result == 'success':
            self.server_response(message, fg='green')
        else:
            raise CommandError(message)

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

        lib_fs = open_fs(args.location)
        package_destination_fs = lib_fs.makedir('__moyapackage__', recreate=True)

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
        lib_name = lib.long_name

        from ..docgen.extracter import Extracter

        extract_fs = TempFS('moyadoc-{}'.format(lib_name))

        extracter = Extracter(archive, extract_fs)
        extracter.extract_lib(lib_name)

        _fh, temp_filename = tempfile.mkstemp('moyadocs')
        with ZipFS(temp_filename, 'w') as docs_zip_fs:
            fs.copy.copy_dir(extract_fs, '/', docs_zip_fs, '/')

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

        message = decode_utf8_bytes(response.headers.get('moya-upload-package-message', ''))
        result = decode_utf8_bytes(response.headers.get('moya-upload-package-result', ''))

        if result == 'success':
            self.server_response(message, fg="green")
        else:
            raise CommandError('upload error ({})'.format(message))
        if result == "success":
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

    def select_packages(self, packages):
        """Select packages from a list of version specs."""
        selected = []
        for _package in packages:
            version_spec = versioning.VersionSpec(_package)
            try:
                select = self.call('package.select', package=_package)
            except jsonrpc.RemoteMethodError as error:
                if error.code == MOYAPI_ERRORS.no_package:
                    select = None
                else:
                    raise
            selected.append((_package, select))
        for _package, package_select in selected:
            if package_select is None:
                version_spec = versioning.VersionSpec(_package)
                raise CommandError("requested package '{}' was not found".format(version_spec.name))
            if package_select['version'] is None:
                raise CommandError("no installation candidate for '{}'".format(_package))
        return selected

    def check_existing(self, package_installs):
        """Check if packages are already installed."""
        if not (self.args.force or self.args.download):
            try:
                application = WSGIApplication(self.location, self.args.settings, disable_autoreload=True, test_build=True)
                archive = application.archive
                if archive is None:
                    raise CommandError('unable to load project, use the --force switch to force installation')
            except Exception as e:
                if not self.args.force:
                    self.console.exception(e)
                    raise CommandError('unable to load project, use the --force switch to force installation')

            for package_name, install_version in package_installs:

                libs = [(lib.long_name, lib.version, lib.install_location)
                        for lib in archive.libs.values() if lib.long_name == package_name]

                for name, version, location in libs:
                    if name == package_name:
                        if version > install_version:
                            raise CommandError("a newer version ({}) of package {} is already installed, use --force to force installation".format(version, name))
                        elif install_version == version:
                            raise CommandError("version {} of {} is already installed, use --force to force installation".format(version, name))
                        else:
                            if not self.args.upgrade:
                                raise CommandError("an older version ({}) of {} is installed, use --upgrade to force upgrade".format(version, name))
            return application
        return None

    def install_packages(self, output_fs, selected_packages, application=None):
        """Install packages"""
        download_fs = TempFS()

        install_packages = []
        for index, (_, select_package) in enumerate(selected_packages):
            app_name = self.args.app or select_package['name'].split('.', 1)[-1].replace('.', '')

            _install = self.download_package(download_fs,
                                             select_package,
                                             app=app_name if index == 0 else None,
                                             mount=self.args.mount if index == 0 else None)
            install_packages.append(_install)

        installed = []

        if application:
            cfg = application.archive.cfg
        else:
            cfg = build.read_config(self.location, self.args.settings)

        changed_server = False
        for _package in install_packages:
            _changed_server, _installed_packages = self.install_package(download_fs,
                                                                        output_fs,
                                                                        _package,
                                                                        cfg=cfg)
            installed.extend(_installed_packages)

            changed_server = changed_server or _changed_server

        table = []
        for _package, mount in installed:
            table.append([Cell("{name}".format(**_package), fg="magenta", bold=True),
                          Cell("{version}".format(**_package)),
                          Cell(_package['location'], fg="blue", bold=True),
                          Cell(mount or '', fg="cyan", bold=True)])

        if table:
            self.console.table(table, ['package', 'version', 'location', 'mount'])

        if application is not None:
            archive = application.archive
            logic_location = archive.cfg.get('project', 'location')
            server_xml = archive.cfg.get('project', 'startup')
            server_xml = archive.project_fs.getsyspath(join(logic_location, server_xml))

            if changed_server:
                self.console.text("moya-pm modified '{}' -- please check changes".format(server_xml), fg="green", bold="yes")

    def install_package(self, download_fs, output_fs, packages, cfg=None):
        args = self.args
        changed_server_xml = False
        installed = []

        for package_name, (app_name, mount, package_select) in packages.items():

            package_name = package_select['name']
            install_version = versioning.Version(package_select['version'])

            filename = "{}-{}.{}".format(package_name, install_version, package_select['md5'])
            download_url = package_select['download']
            #package_filename = download_url.rsplit('/', 1)[-1]

            install_location = relativefrom(self.location,
                                            join(self.location,
                                                 args.output,
                                                 package_select['name']))
            package_select['location'] = install_location

            with download_fs.open(filename, 'rb') as package_file:
                with ZipFS(package_file) as package_fs:
                    with output_fs.makedir(package_select['name'], recreate=True) as lib_fs:
                        lib_fs.removetree('/')
                        fs.copy.copy_dir(package_fs, '/', lib_fs, '/')
                        installed.append((package_select, mount))

            if not args.no_add:
                server_xml = cfg.get('project', 'startup')
                changed_server_xml =\
                    installer.install(project_path=self.location,
                                      server_xml_location=cfg.get('project', 'location'),
                                      server_xml=server_xml,
                                      server_name=args.server,
                                      lib_path=install_location,
                                      lib_name=package_name,
                                      app_name=app_name,
                                      mount=mount)

        return changed_server_xml, installed

    def download_package(self, download_fs, select_package, app=None, mount=None):
        args = self.args

        username = self.settings.get('upload', 'username', None)
        password = self.settings.get('upload', 'password', None)
        if username and password:
            auth = (username, password)
        else:
            auth = None

        _install = "{}=={}".format(select_package['name'], select_package['version'])
        packages = dependencies.gather_dependencies(self.rpc,
                                                    app,
                                                    mount,
                                                    _install,
                                                    self.console,
                                                    no_deps=args.no_deps)

        if not args.no_add:
            for package_name, (app_name, mount, package_select) in packages.items():
                if package_select['version'] is None:
                    raise CommandError("no install candidate for dependency '{}', run 'moya-pm list {}' to see available packages".format(package_name, package_name))

        for package_name, (app_name, mount, package_select) in packages.items():

            package_name = package_select['name']
            install_version = versioning.Version(package_select['version'])

            filename = "{}-{}.{}".format(package_name, install_version, package_select['md5'])
            download_url = package_select['download']
            package_filename = download_url.rsplit('/', 1)[-1]

            with download_fs.open(filename, 'wb') as package_file:
                checksum = downloader.download(download_url,
                                               package_file,
                                               console=self.console,
                                               auth=auth,
                                               verify_ssl=False,
                                               msg="requesting {name}=={version}".format(**package_select))
                if checksum != package_select['md5']:
                    raise CommandError("md5 checksum of download doesn't match server! download={}, server={}".format(checksum, package_select['md5']))

            if args.download:
                with open_fs(args.download) as dest_fs:
                    fs.copy.copy_file(download_fs, filename, dest_fs, package_filename)

        return packages

    def run_install(self):
        args = self.args
        selected_packages = self.select_packages(args.packages)

        package_installs = [(p['name'], versioning.Version(p['version']))
                            for _spec, p in selected_packages]
        application = self.check_existing(package_installs)
        output_path = args.download if args.download is not None else join(self.location, args.output)

        output_fs = OSFS(output_path, create=True)

        self.install_packages(output_fs, selected_packages, application=application)

        for name, package in selected_packages:
            if package['notes']:
                self.console.table([[package['notes']]], ['{name} {version} release notes'.format(**package)])


def main():
    return MoyaPI().run()
