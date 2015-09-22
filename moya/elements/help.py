from __future__ import unicode_literals
from __future__ import print_function

from ..console import make_table_header
from ..tools import extract_namespace
from .. import namespaces
from ..console import Cell
from .. import bbcode

import textwrap


def help(archive, console, tagname):
    """Generate console help"""
    xmlns, tagname = extract_namespace(tagname)
    if '/' not in xmlns:
        xmlns = namespaces.default + '/' + xmlns
    tag = archive.registry.get_tag("{{{}}}{}".format(xmlns, tagname))
    if tag is None:
        if xmlns and not archive.registry.check_namespace(xmlns):
            console.error("No such namespace: %s" % xmlns)
        else:
            console.error("No such tag: %s" % tagname)
        return False
    tag_name = tag._tag_name
    doc = "<%s/>" % tag_name

    doc_attribs = []

    for name, attrib in sorted(tag._tag_attributes.items()):
        if attrib.metavar:
            metavar = attrib.metavar.upper()
            doc_attribs.append('%s="%s"' % (attrib.name or name, metavar))
    if doc_attribs:
        doc = "<%s %s />" % (tag_name, (" ".join(doc_attribs)))
    else:
        doc = "<%s/>" % tag_name

    console.xml(doc.strip()).nl()

    if tag._tag_doc:
        console(bbcode.render_console(tag._tag_doc, max_length=console.width)).nl()

    details = [(Cell("name", bold=True), tagname),
               (Cell('synopsis', bold=True), getattr(tag.Help, 'synopsis', None) if hasattr(tag, 'Help') else ''),
               (Cell("namespace", bold=True), xmlns),
               (Cell("defined", bold=True), getattr(tag, '_definition', '?'))
               ]
    console.table(details, header=False, dividers=False, grid=False).nl()

    if hasattr(tag, 'Help'):
        example = getattr(tag.Help, 'example', None)
        if example:
            example = textwrap.dedent(example)
            console('[example(s)]', fg="magenta", bold=True).nl()
            console.xml(example).nl()

    base_attributes = tag._get_base_attributes()
    params = []
    for name, attrib in tag._tag_attributes.items():
        if name not in base_attributes:
            params.append((Cell('"{}"'.format(name), fg="cyan"),
                          attrib.doc,
                          attrib.type_display.lower(),
                          'Yes' if attrib.required else 'No',
                           attrib.default_display(attrib.default) if not attrib.required else ''
                           ))
    params.sort(key=lambda p: p[0])
    if params:
        console("[attributes]", fg="green", bold=True).nl()
        console.table(make_table_header("attrib", "doc", "type", "required?", "default") + params).nl()

    params = []
    for name, attrib in base_attributes.items():
        if name in tag._tag_attributes:
            docattrib = tag._tag_attributes[name]
        else:
            docattrib = attrib
        params.append((Cell('"{}"'.format(name), fg="cyan"),
                      docattrib.doc,
                      docattrib.type_display.lower(),
                      'Yes' if docattrib.required else 'No',
                       docattrib.default if not docattrib.required else ''
                       ))
    if params:
        console("[inherited attributes]", fg="green", bold=True).nl()
        console.table(make_table_header("attrib", "doc", "type", "required?", "default") + params)

    return True
