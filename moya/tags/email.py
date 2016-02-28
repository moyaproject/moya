from __future__ import unicode_literals
from __future__ import absolute_import

from ..elements.elementbase import Attribute, LogicElement
from ..tags.content import ContentElementMixin
from .. import logic
from .. import namespaces
from ..render import render_object
from ..template.rendercontainer import RenderContainer
from ..mail import Email

import logging
log = logging.getLogger('moya.email')


class EmailElement(LogicElement):
    """Define an email."""
    xmlns = namespaces.email

    class Meta:
        tag_name = "email"

    class Help:
        synopsis = "define an email"

    from_ = Attribute("From email", required=False, default=None, name="from")
    to = Attribute("To email address", type="commalist", required=False, default=None)
    cc = Attribute("CC email address", type="commalist", required=False, default=None)
    bcc = Attribute("BCC email address", type="commalist", required=False, default=None)
    replyto = Attribute("Reply to email address", required=False, default=None)
    subject = Attribute("Email subjects", default=None)


class Text(LogicElement, ContentElementMixin):
    """Add text template to an email."""
    xmlns = namespaces.email

    class Help:
        synopsis = "add text to an email"

    template = Attribute("Template path", type="template", required=False)
    content = Attribute("Content Element", required=False, type="elementref")
    #from_ = Attribute("From email", required=False, default=None, name="from")

    def logic(self, context):
        template, content = self.get_parameters(context, 'template', 'content')
        app = self.get_app(context)
        email = context['email']
        if template:
            template = app.resolve_template(template)
            render_container = RenderContainer.create(app, template=template)
            render_container.update(email.data)
            text = render_object(render_container, self.archive, context, "text")
        else:
            for defer in self.generate_content(context, content, app, td=email.data):
                yield defer
            content = context['.content']
            text = render_object(content, self.archive, context, "text")
        email.text = text


class HTML(LogicElement, ContentElementMixin):
    """Add an HTML template to an email."""
    xmlns = namespaces.email

    class Help:
        synopsis = "add HTML to an email"

    class Meta:
        one_of = [('template', 'content')]

    template = Attribute("Template path", type="template", required=False)
    content = Attribute("Content element", required=False, type="elementref")
    #from_ = Attribute("From email", required=False, default=None, name="from")

    def logic(self, context):
        template, content = self.get_parameters(context, 'template', 'content')
        app = self.get_app(context)
        email = context['email']
        if template:
            template = app.resolve_template(template)
            render_container = RenderContainer.create(app, template=template)
            render_container.update(email.data)
            html = render_object(render_container, self.archive, context, "html")
        else:
            for defer in self.generate_content(context, content, app, td=email.data):
                yield defer
            content = context['_content']
            html = render_object(content, self.archive, context, "html")
        email.html = html


class Get(LogicElement):
    """Get an previously defined email object."""
    xmlns = namespaces.email

    class Help:
        synopsis = "get an email object"

    dst = Attribute("Destination to store exception object", type="reference", required=True)
    email = Attribute("Reference to email tag", type="elementref")
    subject = Attribute("Email subject", default=None)
    data = Attribute("Template / content data", type="expression", default=None)

    from_ = Attribute("From email", required=False, default=None, name="from", map_to="from")
    to = Attribute("To email address", type="commalist", required=False, default=None)
    cc = Attribute("CC email address", type="commalist", required=False, default=None)
    bcc = Attribute("BCC email address", type="commalist", required=False, default=None)
    replyto = Attribute("Reply to email address", required=False, default=None)

    def get_email(self, context):
        dst, data, email_ref, subject, from_ = self.get_parameters(context,
                                                                   'dst',
                                                                   'data',
                                                                   'email',
                                                                   'subject',
                                                                   'from')
        if data is None:
            data = {}
        data.update(self.get_let_map(context))

        with context.data_scope(data):
            app = self.get_app(context)
            email_app, email_element = self.get_element(email_ref, app)

            subject = email_element.subject(context) or subject or ""
            from_ = email_element.get_parameter(context, 'from') or from_ or ""

            emails = email_element.get_parameters_map(context, 'from', 'to', 'cc', 'bcc', 'replyto')
            for k, v in self.get_parameters_map(context, 'from', 'to', 'cc', 'bcc', 'replyto').items():
                if v is not None:
                    emails[k] = v

            email = Email(data=data)
            email.app = email_app
            email.email_element = email_element
            email.subject = subject
            email.set_from(from_)

            for addr in emails['to'] or []:
                email.add_to(addr)
            for addr in emails['cc'] or []:
                email.add_to(addr)
            for addr in emails['bcc'] or []:
                email.add_to(addr)

            email.replyto = emails['replyto']
            return email

    def logic(self, context):
        email = context[self.dst(context)] = self.get_email(context)
        email_app, email_element = self.get_element(self.email(context), self.get_app(context))
        with self.call(context, app=email_app, email=email):
            yield logic.DeferNodeContents(email_element)


class Send(Get):
    """Send an email."""

    class Help:
        synopsis = "send an email"

    xmlns = namespaces.email

    dst = Attribute("Destination to store exception object", type="reference", required=False)
    src = Attribute("Source email", type="index", default=None)
    smtp = Attribute("SMTP server", default='')
    failsilently = Attribute("Should mail exceptions be ignored?", type="boolean", default=True)

    def logic(self, context):
        fail_silently = self.failsilently(context)
        _email = self.src(context)
        if _email is None:
            email = self.get_email(context)
            with self.call(context, app=email.app, email=email):
                yield logic.DeferNodeContents(email.email_element)

        dst = self.dst(context)
        if dst is not None:
            context[self.dst(context)] = email

        if context.get('.debug', False):
            context['.console'].obj(context, email)

        mail_server = self.archive.get_mailserver(self.smtp(context))
        try:
            mail_server.send(email)
            log.info('sent email to "{}", subject "{}"'.format(email.to_text, email.subject or ''))
        except Exception as e:
            log.error('failed to send email to "%s", with subject "%s" (%s)', email.to_text, email.subject or '', e)
            if not fail_silently:
                self.throw('email.send-failed',
                           "Moya was unable to send email '{}' ({})".format(_email, e),
                           diagnosis="Check the [smtp:] section in settings, and that the mail server is running.",
                           info={'email': _email, 'pyerror': e})
