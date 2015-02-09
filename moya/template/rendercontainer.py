from __future__ import unicode_literals

from ..render import HTML


class RenderContainer(dict):
    """A dictionary subclass with template meta information"""

    moya_render_targets = ["html", "text"]

    # def __repr__(self):
    #     return "RenderContainer(%r)" % super(RenderContainer, self).__repr__()

    @classmethod
    def create(cls, app, **meta):
        rc = cls()
        rc._app = app
        rc._meta = meta
        return rc

    def moya_render(self, archive, context, target, options):
        meta = self._meta
        template = meta['template']
        engine = archive.get_template_engine("moya")
        rendered = engine.render(template, self, base_context=context, app=self._app)
        if target == "html":
            return HTML(rendered)
        return rendered
