from __future__ import unicode_literals
from __future__ import print_function

from moya.elements.elementbase import LogicElement, Attribute
from moya import logic
from moya import namespaces

import itertools


class Table(LogicElement):
    """
    Begins a table content definition. Must be inside a [tag]content[/tag] tag.

    """

    class Help:
        synopsis = "add a table to content"
        example = """
        <table class="table table-striped" xmlns="http://moyaproject.com/tables" caption="An example table">
            <columns>
                <header>Product</header>
                <header>Stock</header>
            </columns>
            <rows src="products" dst="product">
                <cell>${product.name}</cell>
                <cell>${product.stock}</cell>
            </rows>
        </table>
        """

    xmlns = namespaces.tables
    template = Attribute("Template", type="template", required=False, default="table.html")
    _class = Attribute("Extra class", required=False, map_to="class", default=None)
    style = Attribute("Option CSS style", required=False)
    _id = Attribute("Table ID", required=False, default=None)
    _from = Attribute("Application", type="application", required=False, default='moya.tables')
    caption = Attribute("Table caption", type="text", required=False, default=None)

    class Meta:
        text_nodes = "text"

    def logic(self, context):
        params = self.get_parameters(context)
        content = context['.content']
        table = {
            "class": params['class'],
            "id": params.id,
            "caption": params.caption,
            "_cols": [],
        }
        app = self.get_app(context)
        css_path = self.archive.get_media_url(context, app, 'media', 'css/tables.css')
        content.include_css(css_path)
        with context.data_scope():
            context['_moyatable'] = table
            with content.template_node("table", app.resolve_template(params.template), {'table': table}):
                yield logic.DeferNodeContents(self)


class Columns(LogicElement):
    """
    Defines the columns in a [tag tables]table[/tag].

    """

    class Help:
        synopsis = "define the columns in a table"

    xmlns = namespaces.tables
    template = Attribute("Template", required=False, default="columns.html")
    headers = Attribute("Headers", required=False, type="commalist", default=None)
    _from = Attribute("Application", type="application", required=False, default='moya.tables')

    def logic(self, context):
        app = self.get_app(context)
        params = self.get_parameters(context)
        content = context['.content']
        with content.template_node('columns', app.resolve_template(params.template), {"headers": params.headers}):
            yield logic.DeferNodeContents(self)


class Header(LogicElement):
    """
    Defines a single column header in a [tag tables]table[/tag].

    """

    class Help:
        synopsis = "define a column header in a table"

    xmlns = namespaces.tables
    template = Attribute("Template", required=False, default="header.html")
    _class = Attribute("Extra class", required=False, map_to="class", default=None)
    _from = Attribute("Application", type="application", required=False, default='moya.tables')
    hide = Attribute("Hide this column?", type="boolean", required=False, default=False)
    align = Attribute("Alignment of column", required=False, choices=['left', 'center', 'right'], default="left")

    class Meta:
        text_nodes = "text"

    def logic(self, context):
        app = self.get_app(context)
        params = self.get_parameters(context)
        content = context['.content']
        td = {'class': params['class'],
              'align': params.align}
        context['_moyatable._cols'].append({'hide': params.hide, 'align': params.align})
        if not params.hide:
            with content.template_node('column', app.resolve_template(params.template), td):
                yield logic.DeferNodeContents(self)


class SortHeader(LogicElement):
    """
    Define a sortable header column in a [tag tables]table[/tag].

    """

    class Help:
        synopsis = "define a sortable header column in a table"

    xmlns = namespaces.tables
    template = Attribute("Template", required=False, default="sortheader.html")
    _class = Attribute("Extra class", required=False, map_to="class", default=None)
    name = Attribute("Name to be set in query string", required=True)
    _from = Attribute("Application", type="application", required=False, default='moya.tables')
    hide = Attribute("Hide this column?", type="boolean", required=False, default=False)
    align = Attribute("Alignment of column", required=False, choices=['left', 'center', 'right'], default="left")

    class Meta:
        text_nodes = "text"

    def logic(self, context):
        app = self.get_app(context)
        params = self.get_parameters(context)
        content = context['.content']
        td = {'class': params['class'],
              'align': params.align,
              'name': params.name}
        context['_moyatable._cols'].append({'hide': params.hide, 'align': params.align})
        if not params.hide:
            with content.template_node('column', app.resolve_template(params.template), td):
                yield logic.DeferNodeContents(self)


class Row(LogicElement):
    """
    Define a row in a [tag tables]table[/tag].

    """

    class Help:
        synopsis = "define a row in a table"

    xmlns = namespaces.tables
    template = Attribute("Template", required=False, default="row.html")
    _class = Attribute("Extra class", required=False, map_to="class", default=None)
    style = Attribute("Option CSS style", required=False)
    _id = Attribute("Table ID", required=False, default=None)
    _from = Attribute("Application", type="application", required=False, default='moya.tables')

    class Meta:
        text_nodes = "text"

    def logic(self, context):
        app = self.get_app(context)
        params = self.get_parameters(context)
        content = context['.content']
        td = {"class": params["class"]}

        with content.template_node('row', app.resolve_template(params.template), td):
            yield logic.DeferNodeContents(self)


class Rows(LogicElement):
    """
    Defines a collection of rows in a [tag tables]table[/tag].

    A [tag tables]rows[/tag] tag may contain either [tag tables]row[/tag] tags [i]or[/i] -- if the [c]src[/c] attribute is set -- [tag tables]cell[/tag] tags.

    When the [c]src[/c] attribute is set, it should be a sequence of values to be iterated over (like [tag]for[/tag]). Each item in the sequence will generate a row containing the enclosed [tag tables]cell[/tag] tags.

    """

    class Help:
        synopsis = "a collection of rows in a table"

    xmlns = namespaces.tables
    template = Attribute("Template", required=False, default="rows.html")
    row_template = Attribute("Template", required=False, default="row.html")
    row_class = Attribute("Extra class for rows", required=False, default=None)
    style = Attribute("Optional CSS style", required=False)
    src = Attribute("Sequence of row data", required=False, type="expression")
    dst = Attribute("Destination", required=False, type="reference")
    _id = Attribute("Table ID", required=False, default=None)
    _from = Attribute("Application", type="application", required=False, default='moya.tables')

    def logic(self, context):
        params = self.get_parameters(context)
        content = context['.content']
        app = self.get_app(context)

        default_col = {'align': 'left'}

        cols = context['_moyatable._cols'] or []
        if self.has_parameter('src'):
            objects, dst = self.get_parameters(context, 'src', 'dst')

            try:
                iter_objects = iter(objects)
            except:
                self.throw('bad-value.src',
                           "row objects attribute {} is not a sequence".format(context.to_expr(objects)),
                           diagnosis="Check the value of the 'objects' attribute is a valid sequence.")

            with content.template_node('rows', app.resolve_template(params.template)):
                for obj in iter_objects:
                    _cols = itertools.chain(cols, itertools.repeat(default_col))
                    if dst:
                        context[dst] = obj
                    td = {'id': self.id(context),
                          'class': self.row_class(context),
                          'style': self.style(context)}
                    with content.template_node("row", app.resolve_template(params.row_template), td):
                        for _col, child in zip(_cols, self.get_children(element_type=('http://moyaproject.com/tables', 'cell'))):
                            if not _col.get('hide', False):
                                with context.data_scope(_col):
                                    yield logic.DeferNode(child)

        else:
            with content.template_node('rows', app.resolve_template(params.template)):
                _cols = itertools.chain(cols, itertools.repeat(default_col))
                for _col, child in zip(_cols, self.get_children(element_type=('http://moyaproject.com/tables', 'cell'))):
                    if not _col.get('hide', False):
                        with context.data_scope(_col):
                            yield logic.DeferNode(child)


class Cell(LogicElement):
    """
    A container for a single cell in a [tag tables]table[/tag].

    """

    class Help:
        synopsis = "a cell in a table"

    xmlns = namespaces.tables
    template = Attribute("Template", required=False, default="cell.html")
    _class = Attribute("Extra class", required=False, map_to="class", default=None)
    _from = Attribute("Application", type="application", required=False, default='moya.tables')
    hide = Attribute("Hide this cell?", type="boolean", required=False, default=False)

    class Meta:
        text_nodes = "text"

    def logic(self, context):
        app = self.get_app(context)
        params = self.get_parameters(context)
        content = context['.content']
        td = {'class': params['class'], 'align': context['align']}

        with content.template_node('cell', app.resolve_template(params.template), td):
            if not params.hide:
                yield logic.DeferNodeContents(self)


# class Header(Cell):
#     """
#     A container for a header cell in a [tag tables]table[/tag].

#     """

#     class Help:
#         synopsis = "add a header cell to a table"

#     xmlns = namespaces.tables
#     template = Attribute("Template", required=False, default="moya.tables/headercell.html")
