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
        name_version = "{} v{}".format(package_select['name'], package_select['version'])
        if dependancy:
            console.text("selected {} (dependency)".format(name_version))
        else:
            console.text("selected {}".format(name_version))
        name = package_select['name']

        requirements[name] = (app_name, mount, package_select)

        if no_deps:
            break

        lib_ini_url = package_select['download'] + '/lib.ini'
        lib_settings_response = requests.get(lib_ini_url, verify=False)
        lib_settings = settings.SettingsContainer.read_from_file(io.StringIO(lib_settings_response.text))

        if 'requires' in lib_settings:
            for dep in lib_settings.get_list('requires', 'install', ''):
                app_name = dep.split('.')[-1]
                package_stack.append((app_name, None, dep))
                dependancy = True
            for dep in lib_settings.get_list('requires', 'mount', ''):
                app_name = dep.split('.')[-1]
                package_stack.append((app_name, "/{}/".format(app_name), dep))

    return requirements


if __name__ == "__main__":
    from moya.console import Console
    rpc = jsonrpc.JSONRPC('https://packages.moyaproject.com/jsonrpc/', ssl_verify=False)
    req = gather_dependencies(rpc, 'moya.logins==0.1.1-beta', Console())
    print(req)
