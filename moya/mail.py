from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from .logic import MoyaException
from .console import Cell
from .tools import summarize_text
from .compat import text_type, string_types


from smtplib import SMTP, SMTPException
from socket import error as socket_error
#from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import logging
log = logging.getLogger('moya.email')


class Email(object):
    """A single email message"""
    def __init__(self, data=None):
        self.headers = {}
        self.data = data or {}
        self.text = None
        self.html = None
        self.subject = None
        setattr(self, 'from', None)
        self.to = []
        self.cc = []
        self.bcc = []
        self.replyto = None
        self.app = None
        self.email_element = None

    @property
    def to_text(self):
        return ','.join(self.to)

    @property
    def cc_text(self):
        return ','.join(self.cc)

    @property
    def bcc_text(self):
        return ','.join(self.bcc)

    def _append_emails(self, dst, emails):
        if emails is None:
            return
        if isinstance(emails, string_types):
            emails = [e.strip() for e in emails.split(',')]
        dst.extend(emails)

    def add_to(self, emails):
        self._append_emails(self.to, emails)

    def add_cc(self, emails):
        self._append_emails(self.cc, emails)

    def add_bcc(self, emails):
        self._append_emails(self.bcc, emails)

    def __moyaconsole__(self, console):
        table = []
        table.append([(Cell("Subject:", bold=True)), self.subject or Cell('No subject', fg="red")])
        if self.to_text:
            table.append([(Cell("To:", bold=True)), self.to_text])
        if self.cc_text:
            table.append([(Cell("Cc:", bold=True)), self.cc_text])
        if self.bcc_text:
            table.append([(Cell("Bcc:", bold=True)), self.bcc_text])
        if self.replyto is not None:
            table.append([(Cell("Reply-To:", bold=True)), self.replyto])
        _from = self.get_from()
        if _from:
            table.append([(Cell("From:", bold=True)), _from])
        if self.text:
            table.append(['text', summarize_text(self.text, max_length=3000)])
        if self.html:
            table.append(['html', summarize_text(self.html, max_length=3000)])
        console.table(table, header=False, dividers=False)

    def set_from(self, value):
        setattr(self, 'from', value)

    def get_from(self):
        return getattr(self, 'from')

    def to_msg(self):
        if self.text is not None and self.html is not None:
            msg = MIMEMultipart('alternative')
        else:
            msg = MIMEMultipart()
        for k, v in self.headers.items():
            msg[k] = v
        if self.subject is not None:
            msg['Subject'] = self.subject
        if self.to:
            msg['To'] = ', '.join(self.to)
        if self.cc:
            msg['Cc'] = ', '.join(self.cc)
        if self.bcc:
            msg['Bcc'] = ', '.join(self.bcc)
        if self.replyto is not None:
            msg['Reply-To'] = self.replyto
        if self.text is not None:
            msg.attach(MIMEText(self.text, 'plain', 'utf-8'))
        if self.html is not None:
            msg.attach(MIMEText(self.html, 'html', 'utf-8'))
        return msg.as_string()


class MailServer(object):
    """Stores SMTP server info and handles sending"""
    def __init__(self,
                 host,
                 name=None,
                 default=False,
                 port=None,
                 local_hostname=None,
                 timeout=None,
                 username=None,
                 password=None,
                 sender=None):
        self.name = name
        self.default = default
        self.host = host
        self.port = port
        self.local_hostname = local_hostname
        self.timeout = timeout
        self.username = username
        self.password = password
        self.sender = sender

    def __repr__(self):
        return '<smtp "{}:{}" "{}">'.format(self.host, self.port, self.name)

    def connect(self):
        """Connect to the smpt server, and login if necessary. Returns an SMTP instance."""
        try:
            smtp = SMTP(self.host, self.port, self.local_hostname, self.timeout)
        except SMTPException as e:
            raise MoyaException("email.error", text_type(e))
        except socket_error as e:
            raise MoyaException("email.connection-refused", text_type(e))

        if self.username:
            try:
                smtp.login(self.username, self.password)
            except smtp.SMTPException as e:
                raise MoyaException("email.auth-fail", text_type(e))
            finally:
                smtp.quit()
        return smtp

    def check(self):
        """Checks connectivity to smtp server. Returns True on success, or throws an exception."""
        smtp = self.connect()
        smtp.quit()
        return True

    def send(self, emails, fail_silently=True):
        """Sends an email, or sequence of emails. Returns the number of failures."""
        if isinstance(emails, Email):
            emails = [emails]
        emails = [(email, email.to_msg()) for email in emails]

        smtp = self.connect()
        try:
            failures = 0
            for email, msg in emails:
                try:
                    sender = text_type(getattr(email, 'from') or self.sender or 'admin@localhost')
                    smtp.sendmail(sender, ', '.join(email.to), msg)
                except SMTPException:
                    if not fail_silently:
                        raise
                    failures += 1
        finally:
            try:
                smtp.quit()
            except SMTPException:
                if not fail_silently:
                    raise
                # What to do here?
                pass
        return failures
