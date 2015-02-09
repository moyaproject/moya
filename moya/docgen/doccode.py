from __future__ import unicode_literals
from __future__ import print_function
import postmarkup


class FieldTag(postmarkup.TagBase):

    def render_open(self, parser, node_index):
        contents = self.get_contents(parser)
        parser.tag_data['doc.' + self.name] = contents
        self.skip_contents(parser)
        return ''


class AsideTag(postmarkup.TagBase):

    def __init__(self, name):
        super(AsideTag, self).__init__(name)

    def render_open(self, parser, node_index):
        return '<div class="aside">'

    def render_close(self, parser, node_index):
        return '</div>'


doccode = postmarkup.create()
doccode.tag_factory.add_tag(FieldTag, "title")
doccode.tag_factory.add_tag(FieldTag, "id")
doccode.tag_factory.add_tag(FieldTag, "section")
doccode.tag_factory.add_tag(AsideTag, "aside")


def render(code):
    data = {}
    body = doccode(code.strip(), paragraphs=True, tag_data=data)
    doc = {}
    for k, v in data.items():
        if k.startswith('doc.'):
            doc[k.split('.', 1)[-1]] = v
    doc['body'] = body
    return doc



if __name__ == "__main__":
    test = """[id]test[/id]
[title]This is the [i]Title![/i][/title]

This is the main content.

[aside]Some aside content here[/aside]

Another paragraph

[code]
import this
[/code]
"""
    print(render(test))
