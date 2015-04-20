from __future__ import unicode_literals
from __future__ import print_function

from fs.opener import fsopendir
from fs.utils import open_atomic_write


def install(project_path, server_xml_location, server_xml, server_name, lib_path, lib_name, app_name, mount=None):
    from lxml.etree import fromstring, ElementTree, parse
    from lxml.etree import XML, Comment

    with fsopendir(project_path) as project_fs:
        with project_fs.opendir(server_xml_location) as server_fs:

            with server_fs.open(server_xml, 'rb') as server_xml_file:
                root = parse(server_xml_file)

            import_tag = XML('<import location="{lib_path}"/><!-- added by moya-pm -->\n\n'.format(lib_path=lib_path))
            import_tag.tail = "\n"

            if mount is not None:
                tag = '<install name="{app_name}" lib="{lib_name}" mount="{mount}" /><!-- added by moya-pm -->'
            else:
                tag = '<install name="{app_name}" lib="{lib_name}" /><!-- added by moya-pm -->'
            install_tag = XML(tag.format(app_name=app_name, lib_name=lib_name, mount=mount))
            install_tag.tail = "\n"

            def has_child(node, tag, **attribs):
                for el in node.findall(tag):
                    if all(el.get(k, None) == v for k, v in attribs.items()):
                        return True
                return False

            server_el = "{{http://moyaproject.com}}server[@docname='{}']".format(server_name)
            for server in root.findall(server_el):
                add_import_tag = not has_child(server,
                                               "{http://moyaproject.com}import",
                                               location=lib_path)
                add_install_tag = not has_child(server,
                                                "{http://moyaproject.com}install",
                                                lib=lib_name)
                if add_import_tag:
                    server.insert(0, import_tag)
                if add_install_tag:
                    server.append(install_tag)

            with open_atomic_write(server_fs, server_xml, 'wb') as server_xml_file:
                root.write(server_xml_file)
    return add_import_tag or add_install_tag
