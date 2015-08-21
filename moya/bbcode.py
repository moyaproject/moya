from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from .compat import implements_to_string
from .html import slugify
from .tools import remove_padding
from .filter import MoyaFilterParams
from . import namespaces

from collections import namedtuple

from fs.path import relativefrom, dirname

import re
import textwrap


class BBCodeError(Exception):
    pass


class MultiReplace(object):
    def __init__(self, repl_dict):
        # string to string mapping; use a regular expression
        keys = sorted(repl_dict.keys(), reverse=True)
        #keys.sort(reverse=True)  # lexical order
        pattern = "|".join([re.escape(key) for key in keys])
        self.pattern = re.compile(pattern)
        self.dict = repl_dict
        self.sub = self.pattern.sub

    def replace(self, s):
        # apply replacement dictionary to string
        get = self.dict.get

        def repl(match):
            item = match.group(0)
            return get(item, item)
        return self.sub(repl, s)

    __call__ = replace


html_escape = MultiReplace({'<': '&lt;',
                            '>': '&gt;',
                            '&': '&amp;',
                            '\n': '<br/>'})


@implements_to_string
class Tag(object):

    inline = True
    enclosed = False
    auto_close = False
    visible = True

    html_open = ""
    html_close = ""

    def __init__(self, name):
        self.name = name

    def __str__(self):
        return "[{}]".format(self.name)

    def match(self, tag_name):
        return tag_name.lower() == self.name

    def on_insert(self, attribs, data):
        self.attribs = attribs

    def render_open(self, data):
        return self.html_open

    def render_close(self, data, text=None):
        return self.html_close


class BlockTag(Tag):
    inline = False


class FieldTag(Tag):
    auto_close = True

    def on_insert(self, attribs, data):
        data[self.name] = attribs


class ParagraphTag(Tag):
    inline = False
    html_open = "<p>"
    html_close = "</p>\n"


class SimpleBlockTag(BlockTag):
    def __init__(self, name, cls):
        super(SimpleBlockTag, self).__init__(name)
        self.html_open = '<div class="{}">'.format(cls)
        self.html_close = '</div>'


class InlineTag(Tag):
    inline = True
    enclosed = False
    auto_close = False
    visible = True

    def __init__(self, name, html_open, html_close):
        super(InlineTag, self).__init__(name)
        self.html_open = html_open
        self.html_close = html_close

    def render_open(self, data):
        return self.html_open

    def render_close(self, data, text=None):
        return self.html_close


class InlineCodeTag(Tag):
    inline = True
    enclosed = True
    auto_close = False
    visible = True

    def render_close(self, data, text=None):
        return '<code>{}</code>'.format(html_escape(text))


class SettingTag(InlineCodeTag):

    def render_close(self, data, text=None):
        if '=' in text:
            k, v = text.split('=', 1)
            k = html_escape(k)
            v = '<span class="value">{}</span>'.format(html_escape(v))
            return '<p class="setting">{}={}</p>'.format(k, v)
        return '<p class="setting">{}</p>'.format(html_escape(text))


class RawTag(Tag):
    inline = True
    visible = True
    enclosed = True

    def render_close(self, data, text=None):
        return text or ''


class AlertTag(BlockTag):
    html_close = "</div>"

    def render_open(self, data):
        html = '<div class="alert alert-warning">'
        if self.attribs.strip():
            html += '<strong>{}</strong> '.format(self.attribs)
        return html


class AsideTag(BlockTag):
    html_close = "</aside>"

    def render_open(self, data):
        html = '<aside>'
        if self.attribs.strip():
            html += '<strong>{}</strong> '.format(self.attribs)
        return html


class NoteTag(BlockTag):
    html_open = '<p class="note">'
    html_close = "</p>"


class CodeTag(BlockTag):
    enclosed = True
    inline = True

    def render_open(self, data):
        self.lang = self.attribs.strip().lower()
        return '''<pre class="moya-console format-{}">'''.format(self.lang)

    def render_close(self, data, text=None):
        from .syntax import highlight
        html = highlight(self.lang, remove_padding(text), line_numbers=False)

        return html + '</pre>'


class H1Tag(BlockTag):
    inline = False
    enclosed = True

    level = 1

    def render_close(self, data, text=None):
        title = text.strip()
        data.setdefault('docmap', []).append([self.level, title])
        h_format = '<h{level}><a name="{anchor}"></a><a href="#{anchor}">{text}<span class="anchor"> &#182;</span></a></h{level}>'
        return h_format.format(text=html_escape(text),
                               level=self.level + 1,
                               anchor=slugify(title))


class H2Tag(H1Tag):
    level = 2


class H3Tag(H1Tag):
    level = 3


class H4Tag(H1Tag):
    level = 4


Index = namedtuple("Index", ['type', 'template', 'lines'])


class IndexTag(BlockTag):
    enclosed = True

    def render_close(self, data, text=None):
        text = text or ''
        index_name = self.attribs.strip() or 'main'
        index_type = '1'
        template = None
        if ' ' in index_name:
            index_name, index_type = index_name.split(' ', 1)
            if ' ' in index_type:
                index_type, template = index_type.split(' ', 1)
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        data.setdefault('indices', {})[index_name] = Index(index_type, template, lines)
        return "{{{" + "INDEX {}".format(index_name) + "}}}"


class URLTag(Tag):
    inline = True

    def render_open(self, data):
        url = self.attribs.strip()
        return '''<a href="{}">'''.format(url)

    def render_close(self, data, text=None):
        return "</a>"


class DocTag(Tag):

    inline = True
    auto_close = True

    _format = '''<a href="{url}">{title}</a>'''

    def render_open(self, data):
        pass

    def render_close(self, data, text=None):
        doc_name = self.attribs.strip()
        fragment = None
        if '#' in doc_name:
            doc_name, fragment = doc_name.split('#', 1)
        if 'docs' not in data:
            return doc_name
        doc = data['docs'].get('doc.{}'.format(doc_name))
        if not doc:
            return doc_name
        title = doc.data.get('title', doc_name)
        urls = data['urls']
        url = urls['doc'].get(doc_name, '')
        if fragment is not None:
            url = url + '#' + fragment
        context = data['context']
        path = dirname(context.get('.request.path', '/'))
        return self._format.format(title=title, url=relativefrom(path, url))


class DocLinkTag(Tag):
    inline = True
    auto_close = False

    def render_open(self, data):
        doc_name = self.attribs.strip()
        anchor = None
        if '#' in doc_name:
            doc_name, anchor = doc_name.split('#', 1)
        if 'docs' not in data:
            return doc_name
        doc = data['docs'].get('doc.{}'.format(doc_name))
        if not doc:
            return doc_name
        title = doc.data.get('title', doc_name)
        urls = data['urls']
        url = urls['doc'].get(doc_name, '')
        context = data['context']
        path = dirname(context.get('.request.path', '/'))
        if anchor:
            url = "{}#{}".format(url, anchor)
        return '''<a href="{url}" title="{title}">'''.format(url=relativefrom(path, url), title=title)

    def render_close(self, data, text=None):
        return "</a>"


class TagTag(BlockTag):
    inline = True
    auto_close = False
    enclosed = True

    _re_namespace = re.compile(r"^\{(.*?)\}(.*?)$")

    @classmethod
    def _join(cls, ns, name):
        if name:
            return "{}/{}".format(ns, name)
        return ns

    def render_open(self, data):
        return ''

    def render_close(self, data, text=None):
        if 'context' not in data:
            return "<code>{}</code>".format(text)
        context = data['context']
        path = dirname(context.get('.request.path', '/'))
        urls = context['.urls']
        tag_name = text.strip()
        xmlns = None
        if '{' in tag_name:
            xmlns, tag_name = self._re_namespace.match(tag_name).groups()
            if '://' not in xmlns:
                xmlns = self._join(namespaces.default, xmlns)
            text = tag_name
            tag_name = "{{{}}}{}".format(xmlns, tag_name)

        if xmlns is None:
            xmlns = self.attribs.strip()
            if '://' not in xmlns:
                xmlns = self._join(namespaces.default, xmlns)
            tag_name = "{{{}}}{}".format(xmlns, tag_name)
        try:
            tag_path = urls['tag'][tag_name]
            relative_tag_path = relativefrom(path, tag_path)
        except KeyError as e:
            return "<code>{}</code>".format(text)
        else:
            return '''<a class="tag" href="{tag_path}">&lt;{text}&gt;</a>'''.format(tag_path=relative_tag_path, text=text)


class DefinitionsTag(BlockTag):

    def render_open(self, data):
        return '<dl class="dl-horizontal">'

    def render_close(self, data, text=None):
        return "</dl>"


class DefineTag(BlockTag):
    inline = True

    def render_open(self, data):
        return '<dt>{}</dt>\n<dd>'.format(html_escape(self.attribs))

    def render_close(self, data, text=None):
        return '</dd>'


class BreakTag(BlockTag):
    inline = True
    auto_close = True

    def render_close(self, data, text=None):
        return "<br>"


_re_remove_markup = re.compile(r'\[.*?\]', re.DOTALL | re.UNICODE)
_re_break_groups = re.compile('[\n]{2,}', re.DOTALL | re.UNICODE)


class BBCode(object):

    standard_replace = MultiReplace({'<': '&lt;',
                                     '>': '&gt;',
                                     '&': '&amp;',
                                     '\n': '<br/>'})

    standard_unreplace = MultiReplace({'&lt;': '<',
                                       '&gt;': '>',
                                       '&amp;': '&'})

    standard_replace_no_break = MultiReplace({'<': '&lt;',
                                              '>': '&gt;',
                                              '&': '&amp;'})

    cosmetic_replace = MultiReplace({'--': '&ndash;',
                                     '---': '&mdash;',
                                     '...': '&#8230;',
                                     '(c)': '&copy;',
                                     '(reg)': '&reg;',
                                     '(tm)': '&trade;'})

    _re_tag_on_line = re.compile(r'\[.*?\]', re.UNICODE)
    _re_end_eq = re.compile(r"\]|\=", re.UNICODE)
    _re_quote_end = re.compile(r'\"|\]', re.UNICODE)
    _re_tag_token = re.compile(r'^\[(\S*?)[\s=]\"?(.*?)\"?\]$', re.UNICODE)
    _re_new_paragraph = re.compile(r'\n*?', re.UNICODE)

    def __init__(self):
        self.registry = []
        self.data = {}
        self.add_tag(ParagraphTag, 'p')

    def add_tag(self, tag_class, *args, **kwargs):
        tag_instance = tag_class(*args, **kwargs)
        self.registry.append(tag_instance)

    @classmethod
    def get_locations(cls, post):
        pos_to_location = {}
        line_start = 0
        for line_no, line in enumerate(post.splitlines(True)):
            line_length = len(line)
            for row in range(line_length):
                pos_to_location[line_start + row] = (line_no, row)
            line_start += line_length
        return pos_to_location

    @classmethod
    def tokenize(cls, post):
        locations = cls.get_locations(post)
        re_tag_on_line = cls._re_tag_on_line
        re_end_eq = cls._re_end_eq
        re_quote_end = cls._re_quote_end
        pos = 0

        def find_first(post, pos, re_ff):
            search = re_ff.search(post, pos)
            if search is None:
                return -1
            return search.start()

        TOKEN_TAG, TOKEN_PTAG, TOKEN_TEXT, TOKEN_PARAGRAPH = range(4)

        def yield_text(text):
            while '\n\n' in text:
                old_paragraph, text = text.split('\n\n', 1)
                if old_paragraph:
                    yield TOKEN_TEXT, old_paragraph
                yield TOKEN_PARAGRAPH, '\n\n'
            if text:
                yield TOKEN_TEXT, text

        post_find = post.find
        while True:
            brace_pos = find_first(post, pos, re_tag_on_line)
            if brace_pos == -1:
                if pos < len(post):
                    for tag_type, text in yield_text(post[pos:]):
                        yield locations[pos], tag_type, text
                    #yield TOKEN_TEXT, post[pos:]
                return
            if brace_pos - pos > 0:
                for tag_type, text in yield_text(post[pos:brace_pos]):
                    yield locations[pos], tag_type, text
                #yield TOKEN_TEXT, post[pos:brace_pos]

            pos = brace_pos
            end_pos = pos + 1

            open_tag_pos = post_find('[', end_pos)
            end_pos = find_first(post, end_pos, re_end_eq)
            if end_pos == -1:
                for tag_type, text in yield_text(post[pos:]):
                    yield locations[pos], tag_type, text
                #yield TOKEN_TEXT, post[pos:]
                return

            if open_tag_pos != -1 and open_tag_pos < end_pos:
                for tag_type, text in yield_text(post[pos:open_tag_pos]):
                    yield locations[pos], tag_type, text
                #yield TOKEN_TEXT, post[pos:open_tag_pos]
                end_pos = open_tag_pos
                pos = end_pos
                continue

            if post[end_pos] == ']':
                yield locations[pos], TOKEN_TAG, post[pos:end_pos + 1]
                pos = end_pos + 1
                continue

            if post[end_pos] == '=':
                try:
                    end_pos += 1
                    while post[end_pos] == ' ':
                        end_pos += 1
                    if post[end_pos] != '"':
                        end_pos = post_find(']', end_pos + 1)
                        if end_pos == -1:
                            return
                        for tag_type, text in yield_text(post[pos:end_pos + 1]):
                            yield locations[pos], tag_type, text
                    else:
                        end_pos = find_first(post, end_pos, re_quote_end)
                        if end_pos == -1:
                            return
                        if post[end_pos] == '"':
                            end_pos = post_find('"', end_pos + 1)
                            if end_pos == -1:
                                return
                            end_pos = post_find(']', end_pos + 1)
                            if end_pos == -1:
                                return
                            yield locations[pos], TOKEN_PTAG, post[pos:end_pos + 1]
                        else:
                            yield locations[pos], TOKEN_TAG, post[pos:end_pos + 1]
                    pos = end_pos + 1
                except IndexError:
                    return

    @classmethod
    def parse_tag_token(cls, s):
        m = cls._re_tag_token.match(s.lstrip())
        if m is None:
            name, attribs = s[1:-1], u''
        else:
            name, attribs = m.groups()
        if name.startswith(u'/'):
            return name.strip()[1:].lower(), attribs.strip(), True
        else:
            return name.strip().lower(), attribs.strip(), False

    # Matches simple blank tags containing only whitespace
    _re_blank_tags = re.compile(r"\<(\w+?)\>\</\1\>")
    _re_blank_with_spaces_tags = re.compile(r"\<(\w+?)\>\s+\</\1\>")
    _re_whitespace_word = re.compile(r"(\s+?\S*)")

    @classmethod
    def cleanup_html(cls, html):
        """Cleans up html. Currently only removes blank tags, i.e. tags containing only
        whitespace. Only applies to tags without attributes. Tag removal is done
        recursively until there are no more blank tags. So <strong><em></em></strong>
        would be completely removed.

        html -- A string containing (X)HTML

        """
        original_html = ''
        while original_html != html:
            original_html = html
            html = cls._re_blank_tags.sub(" ", html)
            html = cls._re_blank_with_spaces_tags.sub(" ", html)
        return html

    def wrap(self, bbcode, max_length=79):
        TOKEN_TAG, TOKEN_PTAG, TOKEN_TEXT, TOKEN_PARAGRAPH = range(4)
        lines = []
        line_length = 0

        bbcode = textwrap.dedent(bbcode.strip('\n'))

        for l in bbcode.splitlines():
            lines.append([])
            line_length = 0
            for loc, tag_type, tag_token in self.tokenize(l):
                #if not lines[-1]:
                #    tag_token = tag_token.lstrip()
                if not tag_token:
                    continue
                if tag_type == TOKEN_TEXT:
                    for word in self._re_whitespace_word.split(tag_token):
                        if not word:
                            continue
                        if line_length + len(word) > max_length:
                            word = word.lstrip()
                            lines.append([word])
                            line_length = len(word)
                        else:
                            lines[-1].append(word)
                            line_length += len(word)
                else:
                    lines[-1].append(tag_token)

        return '\n\n'.join(''.join(word for word in line) for line in lines)

    def render_console(self, bbcode, max_length=79):
        from .console import AttrText, style, XMLHighlighter
        bbcode = self.wrap(bbcode, max_length=min(120, max_length)) + '\n'
        TOKEN_TAG, TOKEN_PTAG, TOKEN_TEXT, TOKEN_PARAGRAPH = range(4)
        _bbcode_map = {
            'b': 'bold',
            'i': 'italic',
            'c': 'bold cyan',
            'u': 'underline',
            'd': 'dim',
            'tag': 'bold cyan',
            'code': 'bold',
            'note': 'italic',
            'error': 'bold red',
            'success': 'bold green'
        }
        tag_stack = []
        text = []
        pos = 0
        attributes = []
        for loc, tag_type, tag_token in self.tokenize(bbcode):
            if tag_type == TOKEN_TEXT:
                text += tag_token
                pos += len(tag_token)
            elif tag_type in (TOKEN_TAG, TOKEN_PTAG):
                tag_name, tag_attribs, end_tag = self.parse_tag_token(tag_token)
                if end_tag:
                    try:
                        if tag_name == tag_stack[-1][0]:
                            tag_name, attribute_start, tag_style = tag_stack.pop()
                            attributes.append((attribute_start, pos, tag_style))
                    except IndexError:
                        raise ValueError("end tag {} doesn't match an opening tag".format(tag_token))
                else:
                    if tag_name in _bbcode_map:
                        tag_style = style(_bbcode_map[tag_name])
                        tag_stack.append((tag_name, pos, tag_style))
                    else:
                        tag_stack.append((tag_name, pos, None))

                        if not self.supports_tag(tag_name):
                            text += tag_token
                            pos += len(tag_token)

            elif tag_type == TOKEN_PARAGRAPH:
                text.append('\n')
                pos += 1

        text = AttrText(''.join(text))
        text = XMLHighlighter.highlight(text)
        for start, end, tag_style in attributes:
            if tag_style is not None:
                text.add_span(start=start, end=end, **tag_style)
        return text

    def render(self, text, data=None, path="?"):
        TOKEN_TAG, TOKEN_PTAG, TOKEN_TEXT, TOKEN_PARAGRAPH = range(4)

        if data is None:
            data = {}

        def raise_error(text):
            raise BBCodeError('File "{}", line {}, col {}: {}'.format(path, line + 1, col + 1, text))

        html = []
        add_html = html.append
        tag_stack = []
        enclosed_text = []
        add_enclosed_text = enclosed_text.append

        def html_escape(s):
            return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

        for (line, col), tag_type, tag_token in self.tokenize(text):
            if tag_stack and tag_stack[-1].enclosed:
                if tag_type in (TOKEN_TAG, TOKEN_PTAG):
                    tag_name, tag_attribs, end_tag = self.parse_tag_token(tag_token)
                    if end_tag and tag_name.lower() == tag_stack[-1].name:
                        try:
                            tag = tag_stack.pop()
                        except IndexError:
                            raise_error("Unexpected close tag: {}".format(tag_token))
                        text = ''.join(enclosed_text)
                        add_html(tag.render_close(data, text=text) or '')
                        del enclosed_text[:]
                    else:
                        add_enclosed_text(tag_token)
                else:
                    add_enclosed_text(tag_token)
                continue

            if tag_type == TOKEN_TEXT:
                if not tag_stack:
                    ptag = self.get_tag("p", '', data)
                    tag_stack.append(ptag)
                    add_html(ptag.render_open(data) or '')
                if not enclosed_text:
                    add_html(self.cosmetic_replace(html_escape(tag_token)))
                else:
                    add_html(html_escape(tag_token))

            elif tag_type == TOKEN_PARAGRAPH:
                if tag_stack and tag_stack[-1].name == "p":
                    tag = tag_stack.pop()
                    add_html(tag.render_close(data) or '')

            elif tag_type in (TOKEN_TAG, TOKEN_PTAG):
                tag_name, tag_attribs, end_tag = self.parse_tag_token(tag_token)

                if end_tag:
                    try:
                        tag = tag_stack.pop()
                    except IndexError:
                        raise_error("unexpected close tag '{}'".format(tag_token))
                    if tag_name.lower() != tag.name:
                        raise_error("mismatched close tag '{}'".format(tag_name))
                    add_html(tag.render_close(data) or '')

                else:
                    tag = self.get_tag(tag_name, tag_attribs, data)
                    if tag is None:
                        raise_error("unknown tag '{}'".format(tag_name))

                    if not tag.inline:
                        while tag_stack:
                            add_html(tag_stack.pop().render_close(data) or '')

                    tag_stack.append(tag)
                    add_html(tag.render_open(data) or '')
                    if tag.auto_close:
                        tag_stack.pop()
                        add_html(tag.render_close(data) or '')

        while tag_stack:
            tag = tag_stack.pop()
            add_html(tag.render_close(data, text='') or '')

        return self.cleanup_html(''.join(html)).strip(), data

    def __call__(self, text):
        html, data = self.render(text)
        return html

    def __repr__(self):
        return "<bbcode parser>"

    def __moyafilter__(self, context, app, value, params):
        data = {'context': context,
                'docs': context.get('.docs', {}),
                'urls': context.get('.urls', {})}
        html, data = self.render(value, data=data, path=params.get('path', 'unknown'))
        return html

    def __moyacall__(self, params):
        return MoyaFilterParams(self, params)

    def supports_tag(self, name):
        return any(tag.match(name) for tag in self.registry)

    def get_tag(self, tag_name, attribs, data):
        for tag_instance in self.registry:
            if tag_instance.match(tag_name):
                tag_instance.on_insert(attribs, data)
                return tag_instance
        return None


parser = BBCode()
add_tag = parser.add_tag
add_tag(InlineTag, 'i', '<em>', '</em>')
add_tag(InlineTag, 'b', '<b>', '</b>')
add_tag(InlineTag, 'u', '<u>', '</u>')
add_tag(InlineTag, 's', '<s>', '</s>')
add_tag(TagTag, 'tag')
add_tag(SettingTag, 'setting')
add_tag(InlineCodeTag, 'c')
add_tag(H1Tag, 'h1')
add_tag(H2Tag, 'h2')
add_tag(H3Tag, 'h3')
add_tag(H4Tag, 'h4')
add_tag(URLTag, 'url')
add_tag(RawTag, 'raw')

add_tag(AlertTag, 'alert')
add_tag(AsideTag, 'aside')
add_tag(NoteTag, 'note')

add_tag(IndexTag, 'index')
add_tag(IndexTag, 'appendix')
add_tag(FieldTag, 'title')
add_tag(FieldTag, 'class')
add_tag(FieldTag, 'section')
add_tag(FieldTag, 'name')
add_tag(FieldTag, 'id')
add_tag(CodeTag, 'code')
add_tag(DocTag, 'doc')
add_tag(DocLinkTag, 'link')
add_tag(DefinitionsTag, 'definitions')
add_tag(DefineTag, 'define')
add_tag(BreakTag, 'br')

render = parser
render_console = parser.render_console


if __name__ == "__main__":
    text = """This is a [i]test[/i] of [b]bbcode[/b] rendering in the console.

    <echo>${hobbits}</echo>

    """
    text = "[h1]te]bst[/c]"
    render(text)
    # from moya.console import Console
    # c = Console()
    # parser.render_console(text)

    # bbcode = "This is long [b]bbcode[/b] that should be wrapped on to multiple lines. Let's see if it [i]works![/i]"
    # print(parser.wrap(bbcode, 30))
