"""Check a Python version specifier against a version of Python

Examples of the version specifier syntax are as follows:

"py"        Any version of Python
"py2"       Any version in the 2.X series
"py2.6"     Only Python version 2.6
"py2.5+"    Python version 2.5 onwards, but only in the Py2.X series
"py3.2+"    Python version 3.2 onwards, but only in the Py3.X series

Version specifiers may be combined with commas. The check function will return True if *any* version passes.

For example:

"py2.5,py2.6"   Matches Python 2.5 and Python 2.6
"py2.7,py3.2+"  Matches Python 2.7 and Python 3.2 onwards

"""
from __future__ import unicode_literals
from __future__ import print_function

import sys
import re


class VersionFormatError(ValueError):
    pass


# Known versions of Python (should be kept up to date)
# Starting from 2.6, since that is the earliest version that Moya requires
known_versions = [(2, 6),
                  (2, 7),
                  (3, 1),
                  (3, 2),
                  (3, 3),
                  (3, 4)]


def check(version_spec, py_version=None, _re_version=re.compile(r'^(py)$|^py(\d)$|^py(\d)\.(\d)$|^py(\d)\.(\d)\+$')):
    """Check a Python version specifier

    `py_version` should be a tuple of (<major version>, <minor version>),
    if it not specified the version of Python will be read from sys.version_info.

    """
    if py_version is None:
        version_info = sys.version_info
        major = version_info.major
        minor = version_info.minor
    else:
        major, minor = py_version
    tokens = [token.strip() for token in version_spec.split(',') if token]
    for version in tokens:
        match = _re_version.match(version)
        if not match:
            raise VersionFormatError("{} is not a valid Py version spec".format(version))
        (all_py,
         absolute_major_version,
         major_version, minor_version,
         major_version_plus, minor_version_plus) = match.groups()
        if (all_py or
           (absolute_major_version and int(absolute_major_version) == major) or
           (major_version and int(major_version) == major and int(minor_version) == minor) or
           (major_version_plus and int(major_version_plus) == major and minor >= int(minor_version_plus))):
                return True
    return False


def list_compatible(version_spec, versions=None):
    """Returns a list of versions compatible with the version spec"""
    if versions is None:
        versions = known_versions
    return [version for version in versions
            if check(version_spec, version)]


if __name__ == "__main__":

    print("Python 2?", check("py2"))
    print("Python 3?", check("py3"))

    tests = ["py", "py2", "py2.6", "py2.6+", "py3"]

    for test in tests:
        print(test, check(test, (2, 7)))

    print(check("py2.5+,py2.6", (2, 7)))
    print(check("py2.7,py3.2+", (3, 3)))

    print(list_compatible('py'))
    print(list_compatible('py2'))
    print(list_compatible('py2.7+,py3'))
    print(list_compatible('py3.2+'))
    print(list_compatible('py2.7,py3.2+'))
