from __future__ import unicode_literals
from __future__ import print_function

from fs.opener import open_fs


def install(project_path, server_xml_location, server_xml, server_name, lib_path, lib_name, app_name, mount=None):
    from lxml.etree import fromstring, ElementTree, parse
    from lxml.etree import XML, Comment

    changes = 0
    with open_fs(project_path) as project_fs:
        with project_fs.opendir(server_xml_location) as server_fs:

            with server_fs.open(server_xml, 'rb') as server_xml_file:
                root = parse(server_xml_file)

            import_tag = XML('<import location="{lib_path}"/>'.format(lib_path=lib_path))
            import_tag.tail = "\n"

            if app_name is None:
                install_tag = XML('<install lib="{lib_name}" />'.format(lib_name=lib_name))
            else:
                install_tag = XML('<install name="{app_name}" lib="{lib_name}" />'.format(app_name=app_name, lib_name=lib_name))

            install_tag.tail = "\n"

            def has_child(node, tag, **attribs):
                for el in node.findall(tag):
                    if all(el.get(k, None) == v for k, v in attribs.items()):
                        return True
                return False

            server_el = "{{http://moyaproject.com}}server[@docname='{}']".format(server_name)
            for server in root.findall(server_el):
                def get_comment():
                    comment = Comment('added by moya-pm')
                    return comment
                if not has_child(server, "{http://moyaproject.com}import", location=lib_path):
                    server.insert(0, import_tag)
                    server.insert(0, get_comment())
                    changes += 1
                if not has_child(server, "{http://moyaproject.com}install", lib=lib_name):
                    server.append(Comment('added by moya-pm'))
                    server.append(install_tag)
                    changes += 1
                    if mount is not None and app_name is not None:
                        if not has_child(server, "{http://moyaproject.com}mount", app_name=app_name):
                            mount_tag = XML('<mount app="{app_name}" url="{mount}" />'.format(app_name=app_name, mount=mount))
                            mount_tag.tail = '\n'
                            server.append(get_comment())
                            server.append(mount_tag)
                            changes += 1

            with server_fs.open(server_xml, 'wb') as server_xml_file:
                root.write(server_xml_file)
    return bool(changes)
