from __future__ import unicode_literals
from __future__ import print_function

from ..elements.elementbase import LogicElement, Attribute
from ..tags.context import DataSetter
from ..interface import AttributeExposer
from ..compat import iteritems, text_type


class Feed(AttributeExposer):

    __moya_exposed_attributes__ = ['format', 'title', '_items', 'channel', 'xml']

    def __init__(self, format, url, title, description, link, **kwargs):
        self.format = format
        self.url = url
        self.channel = kwargs
        self.channel.update(title=title, description=description, link=link)
        self._items = []
        super(Feed, self).__init__()

    def __repr__(self):
        return "<feed-{} '{}'>".format(self.format, self.title)

    @property
    def title(self):
        return self.channel.get('title', None)

    def add_item(self, item):
        self._items.append(item)

    @property
    def xml(self):
        return self.to_xml()

    def to_xml(self):
        from lxml import etree as ET
        feed = ET.Element('rss', version="2.0", nsmap={'atom': 'http://www.w3.org/2005/Atom'})
        channel = ET.SubElement(feed, 'channel')
        ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link", href=self.url, type="application/rss+xml", rel="self")
        for k, v in iteritems(self.channel):
            if v:
                node = ET.SubElement(channel, k)
                node.text = text_type(v)

        for item in self._items:
            item_node = ET.SubElement(channel, 'item')
            for k, v in iteritems(item):
                if v is not None:
                    node = ET.SubElement(item_node, k)
                    node.text = v
        xml = ET.tostring(feed, encoding='utf-8')
        return xml

    def __xml__(self):
        return self.to_xml()


# http://validator.w3.org/feed/docs/rss2.html
class FeedElement(DataSetter):
    """
    Create a [url http://en.wikipedia.org/wiki/RSS]RSS[/url] Feed object.

    You can add items to a feed with [tag]add-feed-item[/tag].

    """

    class Help:
        synopsis = "create an RSS feed"
        example = """
        <view libname="view.feed">
            <!-- create feed object -->
            <get-fq-url name="list" dst="blog_url" />
            <feed title="${.app.settings.title or 'blog'}"
                description="${.app.settings.description or 'blog feed'}"
                link="${blog_url}" dst="feed"/>

            <db:query model="#Post" dst="posts" orderby="-published_date"
                filter="#Post.published==True" maxresults="25"/>

            <!-- add items -->
            <for src="posts" dst="post">
                <get-fq-url name="showpost" let:slug="post.slug" dst="post_url"/>
                <process-markup src="post.content" type="${.app.settings.default_markup}" dst="description"/>
                <add-feed-item src="feed"
                    title="post.title" link="post_url" description="description"
                    pub_date="post.published_date"/>
            </for>

            <!-- serve feed XML -->
            <serve-xml content_type="application/rss+xml" obj="feed"/>
        </view>
        """

    class Meta:
        tag_name = "feed"

    dst = Attribute("Destination object", type="reference", default=None)

    title = Attribute("Title of Feed", required=True)
    description = Attribute("Description of feed", required=True)
    link = Attribute("Link", required=True, default=None)
    language = Attribute("Language", required=False, default=None)

    def logic(self, context):
        params = self.get_parameters(context)
        optional = {}
        if params.language is None:
            lang = context['.locale.language']
            if lang:
                optional['language'] = text_type(lang)
        optional = self.get_let_map(context)
        if 'generator' not in optional:
            optional['generator'] = text_type(context['.app.lib.version_name'])
        feed = Feed(format='rss',
                    url=context['.request.url'],
                    title=params.title,
                    description=params.description,
                    link=params.link,
                    **optional)
        self.set_context(context, params.dst, feed)


class AddFeedItem(LogicElement):
    """
    Add an item to a [tag]feed[/tag].
    """

    class Help:
        synopsis = "add an item to an RSS feed"

    class Meta:
        one_of = [('title', 'description')]

    src = Attribute("feed to add to", type="expression", required=True)
    title = Attribute("Title of Feed", type="expression", required=False)
    link = Attribute("Link to this item on the web", type="expression", required=True, default=None)
    description = Attribute("Item description", type="expression", required=False)
    author = Attribute("Email address of the author of this item", type="expression", required=False, default=None)
    category = Attribute("Includes the item in one or more categories", type="expression", required=False, default=None)
    guid = Attribute("A string that uniquely identifies the item.", type="expression", required=False, default=None)
    pub_date = Attribute("Indicates when the item was published", type="expression", required=False, default=None)

    _item_names = [('title', None),
                   ('link', None),
                   ('description', None),
                   ('author', None),
                   ('category', None),
                   ('guid', None),
                   ('pub_date', 'pubDate')]

    def logic(self, context):
        params = self.get_parameters(context)
        item = {}
        for name, item_name in self._item_names:
            if self.has_parameter(name):
                if item_name is None:
                    item_name = name
                item[item_name] = params[name]

        if 'pubDate' in item:
            dt = item['pubDate']
            if hasattr(dt, 'rfc2822'):
                item['pubDate'] = dt.rfc2822

        if 'guid' not in item:
            guid = item.get('link', None)
            item['guid'] = guid

        feed = params.src
        try:
            feed.add_item(item)
        except Exception as e:
            self.throw('add-feed-item.add-fail', 'unable to add feed item ({})'.format(e))
