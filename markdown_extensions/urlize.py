"""
Urlize Extension for Python-Markdown
=============================================
Automatically text links parsing to html links
Examples:
    http://google.com
    www.google.co
    google.com
"""

from markdown.extensions import Extension
from markdown.inlinepatterns import Pattern
from markdown.util import AtomicString, etree


class UrlizePattern(Pattern):
    RE = '(?P<url>%s)' % '|'.join([
        r'<(?:f|ht)tps?://[^>]*>',
        r'\b(?:f|ht)tps?://[^)<>\s]+[^.,)<>\s]',
        r'[^(<\s]+\.(?:[a-z]{2,6})/[^)<>\s]+[^.,)<>\s]',
        r'[^(<\s]+\.(?:[a-z]{2,6})\b',
        r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,4}\b'
    ])

    def __init__(self, md):
        super(UrlizePattern, self).__init__(self.RE, md)

    def handleMatch(self, m):
        url = m.group('url')

        if url.startswith('<'):
            url = url[1:-1]

        text = url

        el = etree.Element("a")
        el.text = AtomicString(text)

        if not url.split('://')[0] in ('http', 'https', 'ftp'):
            if '@' in url and not '/' in url:
                url = 'mailto:' + url
            else:
                url = 'http://' + url
                el.set('target', '_blank')

        el.set('href', url)
        return el


class UrlizeExtension(Extension):
    def extendMarkdown(self, md, md_globals):
        md.inlinePatterns.add(
            'autolink', UrlizePattern(md), '_end',
        )


def makeExtension(*args, **kwargs):
    return UrlizeExtension(*args, **kwargs)
