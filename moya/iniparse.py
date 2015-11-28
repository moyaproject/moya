# PY2 + PY3
from __future__ import unicode_literals
from __future__ import unicode_literals

from .compat import text_type, iteritems
from .containers import OrderedDict

import os
import re

re_section = re.compile(r'\[(.*?)\]', re.UNICODE)


def sub_env(text, _re_env=re.compile(r'\$(\w+)', re.MULTILINE)):
    """Substition renvironment, in $ENV_VARIABLE syntax"""
    get_environ = os.environ.get

    def repl(match):
        return get_environ(match.group(1), match.group(0))
    return _re_env.sub(repl, text)


def parse(inifile, sections=None, section_class=OrderedDict, _sub_env=sub_env):
    """Parse an ini file in to nested dictionaries"""
    if hasattr(inifile, "read"):
        ini = inifile.read()
    else:
        ini = inifile
    if not isinstance(ini, text_type):
        ini = ini.decode('utf-8')
    inilines = ini.splitlines()

    if sections is None:
        sections = section_class()
    current_section = ''
    current_section_data = section_class()
    current_key = None
    current_value = ''

    section_match = re_section.match

    for line in inilines:
        if line.startswith('#'):
            continue
        if not line.strip():
            current_key = None
            continue
        match = section_match(line)
        if match:
            sections[current_section] = current_section_data
            current_section_data = section_class()
            current_section = match.group(1)
        elif line[0] in ' \t':
            if current_key is not None:
                current_value += '\n' + line.strip()
                current_section_data[current_key] = current_value
        elif '=' in line:
            key, value = line.split('=', 1)
            key = key.rstrip()
            value = _sub_env(value.lstrip()).lstrip()
            current_key = key
            current_value = value
            current_section_data[key] = value
        else:
            current_section_data[line.strip()] = ''

    sections[current_section] = current_section_data
    return sections


def write(settings, comments=None):
    """Write an ini file from nested dictionaries"""
    if comments is None:
        comments = []
    if isinstance(comments, text_type):
        comments = comments.splitlines()
    lines = ["# " + comment for comment in comments]

    def write_section(name, section):
        if name:
            lines.append("[{}]".format(name))
        for k, v in iteritems(section):
            v = "\n    ".join(v.split('\n'))
            lines.append("{k} = {v}".format(k=k, v=v))
        lines.append('')

    if '' in settings:
        write_section('', settings[''])

    for name, section in iteritems(settings):
        if name:
            write_section(name, section)

    return '\n'.join(lines)


if __name__ == "__main__":

    ini = """# -------------------------------------------------------------
# Filesystems
# -------------------------------------------------------------

foo=bar

[fs:project]
location = ./
multiline = long
    line

[templateengine:jinja2]
cachefs = jinja2cache

[templates:default]
location = ./templates
priority = 10

[app:blog]
name = Will's blog
value = 3

noequal=

"""

    settings = parse(ini)

    settings["new"] = {"foo": "bar\nbaz"}

    print(write(settings, comments=["Re-written ini file", "comments"]))
