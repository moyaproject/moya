from __future__ import unicode_literals
from __future__ import print_function

from moya.elements.elementbase import LogicElement, Attribute
from moya import logic
from moya import namespaces


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
            "caption": params.caption
        }
        app = self.get_app(context)
        css_path = self.archive.get_media_url(app, 'media', 'css/tables.css')
        content.include_css(css_path)
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

    class Meta:
        text_nodes = "text"

    def logic(self, context):
        app = self.get_app(context)
        params = self.get_parameters(context)
        content = context['.content']
        td = {'class': params['class']}
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

    class Meta:
        text_nodes = "text"

    def logic(self, context):
        app = self.get_app(context)
        params = self.get_parameters(context)
        content = context['.content']
        td = {'class': params['class'],
              'name': params.name}
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

        if self.has_parameter('src'):
            objects, dst = self.get_parameters(context, 'src', 'dst')

            with content.template_node('rows', app.resolve_template(params.template)):
                for obj in objects:
                    if dst:
                        context[dst] = obj
                    td = {'id': self.id(context),
                          'class': self.row_class(context),
                          'style': self.style(context)}
                    with content.template_node("row", app.resolve_template(params.row_template), td):
                        yield logic.DeferNodeContents(self)

        else:
            with content.template_node('rows', app.resolve_template(params.template)):
                yield logic.DeferNodeContents(self)


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

    class Meta:
        text_nodes = "text"

    def logic(self, context):
        app = self.get_app(context)
        params = self.get_parameters(context)
        content = context['.content']
        td = {'class': params['class']}
        with content.template_node('cell', app.resolve_template(params.template), td):
            yield logic.DeferNodeContents(self)


# class Header(Cell):
#     """
#     A container for a header cell in a [tag tables]table[/tag].

#     """

#     class Help:
#         synopsis = "add a header cell to a table"

#     xmlns = namespaces.tables
#     template = Attribute("Template", required=False, default="moya.tables/headercell.html")
