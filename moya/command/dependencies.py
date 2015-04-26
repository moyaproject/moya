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


def gather_dependencies(rpc, package, console, no_deps=False):

    visited = set()
    package_stack = [package]

    requirements = OrderedDict()
    dependancy = False

    while package_stack:
        package = package_stack.pop()
        if package in visited:
            continue
        visited.add(package)

        if dependancy:
            console.text("selecting '{}' (dependency)".format(package))
        else:
            console.text("selecting '{}'".format(package))
        package_select = rpc.call('package.select', package=package)
        name = package_select['name']
        version = package_select['version']

        requirements[name] = package_select

        if no_deps:
            break

        lib_ini_url = package_select['download'] + '/lib.ini'
        lib_settings_response = requests.get(lib_ini_url, verify=False)
        lib_settings = settings.SettingsContainer.read_from_file(io.StringIO(lib_settings_response.text))

        if 'dependencies' in lib_settings:
            for dep in lib_settings.get('dependencies', 'install', []):
                package_stack.append(dep)
                dependancy = True

    return requirements


if __name__ == "__main__":
    from moya.console import Console
    rpc = jsonrpc.JSONRPC('https://packages.moyaproject.com/jsonrpc/', ssl_verify=False)
    req = gather_dependencies(rpc, 'moya.logins==0.1.1-beta', Console())
    print(req)

