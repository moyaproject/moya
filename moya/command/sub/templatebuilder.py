"""A system to create a directory tree from a template.

The format is very simple. A line beginning with @ should be a path to a file. Subsequent lines after that line will be appended to the specified file.

The template is passed through moya templates, creating a very flexible system for dynamically creating file trees.

In order to allow these fs templates to generate moya templates, the syntax is slightly different.
The filesystem template syntax should be {{% %}} for logic, and ${{ }} for substitution.


"""


from __future__ import unicode_literals
from __future__ import print_function

from ...context import Context
from ...template.moyatemplates import Template

from fs.path import dirname, join, relpath

import re


def compile_fs_template(fs, template_text, data=None, path=None):
    """Compile a fs template structure in to a filesystem object"""
    if data is None:
        data = {}
    template = Template(template_text)
    template.re_special = re.compile(r'\{\{\%((?:\".*?\"|\'.*?\'|.|\s)*?)\%\}\}|(\{\{\#)|(\#\}\})')
    context = Context(re_sub=r'\$\{\{(.*?)\}\}')
    #with context.frame("data"):
    fs_template = template.render(data, context=context)

    out_type = None
    out_filename = None
    file_lines = []

    def write_file(filename, file_type):
        if filename:
            if file_type.lower() == "text":
                with fs.open(filename, 'wt') as f:
                    f.write('\n'.join(file_lines) + '\n')
            elif file_type.lower() == "wraptext":
                import textwrap
                with fs.open(filename, 'wt') as f:
                    for line in file_lines:
                        f.write('\n'.join(textwrap.wrap(line, 79)) + '\n')
            elif file_type.lower() == "bin":
                with fs.open(filename, 'wb') as f:
                    for line in file_lines:
                        chunk = b''.join(chr(int(a + b, 16)) for a, b in zip(line[::2], line[1::2]))
                        f.write(chunk)

            del file_lines[:]

    for line in fs_template.splitlines():
        line = line.rstrip()
        if line.startswith('@'):
            write_file(out_filename, out_type)
            out_filename = None
            out_type, path_spec = line[1:].split(' ', 1)
            if path:
                path_spec = join(path, relpath(path_spec))
            if path_spec.endswith('/'):
                fs.makedirs(path_spec, recreate=True)
                out_filename = None
            else:
                fs.makedirs(dirname(path_spec), recreate=True)
                out_filename = path_spec
            continue
        if out_filename:
            file_lines.append(line)
    if out_filename:
        write_file(out_filename, out_type)


if __name__ == "__main__":
    template = """
@test.txt
This
is a test file
{{%- if readme %}}
@readme.txt
Readme file
-----------
${{message}}
{{%- endif %}}
@templates/base.html
<h1>${title}</h1>
<ul>
    {% for fruit in fruits %}
    <li>${fruit}</li>
    {% endfor %}
</ul>
@settings/production.ini
@foo/bar/baz/
@author
Bob
    """

    from fs.osfs import OSFS
    from fs.memoryfs import MemoryFS

    fs = OSFS('__test__', create=True)
    fs = MemoryFS()
    td = dict(message="Hello, World!", readme=True)
    compile_fs_template(fs, template, td)

    fs.tree()
