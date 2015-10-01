"""Manage Moya version comparisons


Moya version numbers used in libraries consist of one to three integers separated by dots. If there are less than three components, then they are assumed to be equal to 0.

Version numbers may also be appended with a hyphen and string to indicate the pre-release version.

For example:

   0.1
   1.2.23
   0.9-beta
   1.0-rc

The left most number is the most significant (matched first). Versions with a different pre-release version will never match.

Version specs are used to specify a required version of the library.
Version specs consist of the name of a library, followed by a number of comparisons.
A comparison consists of an operator (==, >, <= etc) followed by a version. e.g.:

    moya.auth==1.0
    moya.auth>=0.5<1.0
    acmesoft.kitchen.sink>=2.1

A version spec without an operator will match any version, e.g.:

    moya.auth

If multiple versions match, the most up-to-date will be returned.

"""
from __future__ import unicode_literals
from __future__ import print_function

from moya.interface import AttributeExposer
from moya.compat import text_type, implements_to_string, zip_longest, cmp


import re


_re_version = re.compile(r'^([\d\.]+)(?:\-([0-9A-Za-z-\.]+))?$')
_re_version_spec = re.compile(r'^([\w\.\-]+)((?:(?:==|>=|<=|>|<|\!=)[\d\.0-9A-Za-z-]*)*)$')
_re_version_compare = re.compile(r'(==|>=|<=|>|<|\!=)([\d\.0-9A-Za-z-]*)')


class VersionFormatError(ValueError):
    def __init__(self, v, msg=None):
        if msg is None:
            msg = "version format should be MAJOR.MINOR.PATCH or MAJOR.MINOR.PATCH-RELEASE (not '{}')".format(v)
        return super(VersionFormatError, self).__init__(msg)


class VersionSpecFormatError(ValueError):
    def __init__(self, v):
        return super(VersionSpecFormatError, self).__init__("version specification '{}' is badly formatted".format(v))


@implements_to_string
class VersionSpec(AttributeExposer):
    """A string that specifies valid versions"""

    __moya_exposed_attributes__ = ['name',
                                   'normalized',
                                   'comparisons']

    def __init__(self, spec):
        version_match = _re_version_spec.match(spec)
        if version_match is None:
            raise VersionSpecFormatError(spec)
        name, comparisons = version_match.groups()
        self.name = name
        self.comparisons = [(c, Version(v)) for c, v in _re_version_compare.findall(comparisons)]

    def __repr__(self):
        return 'VersionSpec("{}")'.format(self)

    def __moyarepr__(self, context):
        return "versionspec:'{}'".format(self.normalized)

    def __moyajson__(self):
        return self.normalized

    def __moyadbobject__(self):
        return self.normalized

    def __str__(self):
        return self.normalized

    @property
    def normalized(self):
        return "{}{}".format(self.name, ''.join(c + text_type(v) for c, v in self.comparisons))

    def compare(self, version):
        """Compare with a version, return True if the version matches the specification"""
        version = Version(version)
        if not self.comparisons and version.release:
            return False
        return all(version.compare(c, v) for c, v in self.comparisons)

    __call__ = compare

    def __contains__(self, version):
        """Syntactic sugar so you can do if (version in version_spec)."""
        return self.compare(version)

    def filter(self, versions, sort=True):
        """Filter out versions that don't match the spec"""
        versions = [v for v in versions if self.compare(v)]
        if sort:
            versions.sort(key=Version)
        return versions

    def get_highest(self, versions):
        """Get the highest version which matches, or return None"""
        try:
            return max(Version(v) for v in versions if self.compare(v))
        except ValueError:
            return None


@implements_to_string
class Version(AttributeExposer):
    """A single version number with overloaded comparisons"""

    __moya_exposed_attributes__ = ['release',
                                   'number',
                                   'text',
                                   'major',
                                   'minor',
                                   'patch',
                                   'release',
                                   'tuple',
                                   'base']

    @classmethod
    def _cmp_seq(cls, v1, v2):
        """Compares a version sequence, padded with zeros to be the same size"""
        for a, b in zip_longest(v1, v2, fillvalue=0):
            # If types are different, treat them as text
            if type(a) != type(b):
                a = text_type(a)
                b = text_type(b)
            c = cmp(a, b)
            if c:
                return c
        return 0

    def __init__(self, v):
        if isinstance(v, Version):
            self.release = v.release[:]
            self.number = v.number[:]
        else:
            version_match = _re_version.match(v.strip())
            if version_match is None:
                raise VersionFormatError(v)

            version_text, release = version_match.groups()

            if release:
                self.release = [int(r) if r.isdigit() else r for r in release.split('.')]
            else:
                self.release = []
            try:
                number_tokens = version_text.split('.')
                if len(number_tokens) > 3:
                    raise VersionFormatError(v)
                if len(number_tokens) < 3:
                    number_tokens += ['0'] * (3 - len(number_tokens))
                self.number = [int(component) for component in number_tokens]
            except ValueError:
                raise VersionFormatError(v)

    @classmethod
    def sorted(cls, versions, reverse=False):
        """Sorts a sequence of version numbers"""
        return sorted(versions, key=cls, reverse=reverse)

    def __moyarepr__(self, context):
        return "version:'{}'".format(self.text)

    def __repr__(self):
        return 'Version("{}")'.format(self.text)

    def __moyajson__(self):
        return self.text

    def __moyadbobject__(self):
        return self.text

    def __str__(self):
        return self.text

    @property
    def text(self):
        text = ".".join(text_type(n) for n in self.number)
        if self.release:
            text += "-{}".format('.'.join(text_type(t) for t in self.release))
        return text

    def _cmp(self, other):
        other = Version(other)
        _cmp = self._cmp_seq(other.number, self.number)
        if _cmp:
            return _cmp
        if other.release and not self.release:
            return -1
        if self.release and not other.release:
            return + 1
        if other.release or self.release:
            return self._cmp_seq(other.release, self.release)
        return 0

    def __eq__(self, other):
        other = Version(other)
        if self.release != other.release:
            return False
        return self.tuple == other.tuple

    def __ne__(self, other):
        other = Version(other)
        if self.release == other.release:
            return True
        return self.tuple != other.tuple

    def __gt__(self, other):
        return self._cmp(other) == -1

    def __ge__(self, other):
        return self._cmp(other) in (0, -1)

    def __lt__(self, other):
        return self._cmp(other) == +1

    def __le__(self, other):
        return self._cmp(other) in (0, +1)

    @property
    def tuple(self):
        if self.release:
            return tuple(self.number + self.release)
        return tuple(self.number)

    @property
    def major(self):
        return self.number[0]

    @property
    def minor(self):
        return self.number[1]

    @property
    def patch(self):
        return self.number[2]

    @property
    def base(self):
        if self.release:
            return "{}.{}-{}".format(self.major, self.minor, '.'.join(text_type(r) for r in self.release))
        else:
            return "{}.{}".format(self.major, self.minor)

    _comparisons = {'': lambda v1, v2: True,
                    '==': __eq__,
                    '!=': __ne__,
                    '>': __gt__,
                    '>=': __ge__,
                    '<': __lt__,
                    '<=': __le__}

    def compare(self, comparison, version):
        v = Version(version)
        return self.release == v.release and self._comparisons[comparison](self, v)


if __name__ == "__main__":

    print(Version("0.1.2-dev") >= Version("0.1.2-dev"))

    print(VersionSpec("dave.test.project==1.0"))
    print(VersionSpec("dave.test.project==1.0-dev"))
    v = VersionSpec("moya.auth>=0.1.5<1.0!=0.1.9")
    print(v)

    print(v.compare('0.1.9'))
    print(v.compare('0.2.0'))
    print(v.compare('0.9.9'))
    print(v.compare('1.0'))

    print(Version("1.2-beta"))
    versions = ["0", "1", "0.1", "0.2", "0.2.0-dev", "0.1.1", "0.2.0-dev.1", "0.2.0-dev.2", "0.2.0-2", "0.1.6", "1.0", "0.1.9", "0.5", "0.9.23", "1.1.0"]
    print("sorted", Version.sorted(versions))
    print(v.filter(versions))
    print(v.get_highest(versions))
    v = VersionSpec("moya.auth")
    print(v)

    print(Version("1.3.4-beta").tuple)

    print()
    v = Version("1.2-dev.2")
    print(v)
    print(v > "1.1-dev")
    print("1.3-dev" > v)
    print(repr(v))
    print(v.major)
    print(v.minor)
    print(v.patch)
    print(v.tuple)
    print(v.number)
    print(v.release)
    print(v.text)
    print(v.base)
