import html
import html.parser as html_parser

from django.template import Context, Template


class BaseRenderer(object):

    def __init__(self, template):
        self._template = template
        self._html_parser = html_parser.HTMLParser()
        self._template_text = template.text

    @property
    def text_template(self):
        return Template(self._template_text)

    def render(self, context):
        raise NotImplementedError


class SMSMessageRenderer(BaseRenderer):

    def render(self, context):
        return html.unescape(s=self.text_template.render(Context(context)))


class EmailMessageRenderer(BaseRenderer):

    def __init__(self, template):
        super(EmailMessageRenderer, self).__init__(template)
        self._template_html = template.html_text
        self._subject = template.subject

    @property
    def html_template(self):
        return Template(self._template_html)

    @property
    def subject(self):
        return Template(self._subject)

    def render(self, context):
        context = Context(context)
        text = self.text_template.render(context)
        html = self.html_template.render(context)
        subject = self.subject.render(context)

        return text, subject, html
