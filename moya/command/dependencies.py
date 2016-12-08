"""
Manage Moya package dependencies

"""

from __future__ import unicode_literals
from __future__ import print_function

from moya import jsonrpc
from moya import settings
from moya import versioning
from collections import OrderedDict

import io
import requests


class DependencyError(Exception):
    pass


def gather_dependencies(rpc, app_name, mount, package, console, no_deps=False):

    visited = set()
    package_stack = [(app_name, mount, package)]

    requirements = OrderedDict()
    dependancy = False

    while package_stack:
        app_name, mount, package = package_stack.pop()
        if package in visited:
            continue
        visited.add(package)

        package_select = rpc.call('package.select', package=package)

        if dependancy and package_select['version'] is None:
            console.text("dependency '{}' has no installation candidate".format(package), fg="red")
            continue

        name_version = "{} {}".format(package_select['name'], package_select['version'])
        if dependancy:
            console.text("selected {} (dependency)".format(name_version), italic=True)
        else:
            console.text("selected {}".format(name_version), italic=True)
        name = package_select['name']

        requirements[name] = (app_name, mount, package_select)

        if no_deps:
            break

        lib_ini_url = package_select['download'] + '/lib.ini'
        lib_settings_response = requests.get(lib_ini_url, verify=False)
        lib_settings = settings.SettingsContainer.read_from_file(io.StringIO(lib_settings_response.text))

        def make_app_name(dep):
            long_name = versioning.VersionSpec(dep).name
            return long_name.split('.', 1)[-1].replace('.', '')

        if 'requires' in lib_settings:
            for dep in lib_settings.get_list('requires', 'install', ''):
                app_name = make_app_name(dep)
                package_stack.append((app_name, None, dep))
                dependancy = True
            for dep in lib_settings.get_list('requires', 'mount', ''):
                app_name = make_app_name(dep)
                package_stack.append((app_name, "/{}/".format(app_name), dep))

    return requirements


if __name__ == "__main__":
    from moya.console import Console
    rpc = jsonrpc.JSONRPC('https://packages.moyaproject.com/jsonrpc/', ssl_verify=False)
    req = gather_dependencies(rpc, 'moya.logins==0.1.1-beta', Console())
    print(req)
