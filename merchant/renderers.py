from datetime import date, datetime, time, timedelta

from django.template import Context, Template, TemplateSyntaxError
from django.utils import timezone


class ScreenTextRenderer(object):
    def __init__(self, screen_text):
        self.screen_text = screen_text

    def render(self, context):
        context = Context(context)
        rendered_screen_text = {}
        for key, template in self.screen_text.items():
            try:
                rendered_screen_text[key] = Template(template).render(context=context)
            except TemplateSyntaxError:
                rendered_screen_text[key] = None

        return rendered_screen_text

    @staticmethod
    def get_context_example():
        delivery_interval = (timezone.now() + timedelta(hours=10)).strftime('%-I:%M %p')
        delivery_interval += ' - ' + (timezone.now() + timedelta(hours=12)).strftime('%-I:%M %p')

        return {
            'delivery_day_short': (timezone.now() + timedelta(hours=12)).date().strftime('%e %B'),
            'delivery_day_full': (timezone.now() + timedelta(hours=12)).date().strftime('%e %B %Y'),
            'delivery_interval': delivery_interval,
            'queue': 123,
            'merchant': 'Merchant',
            'customer_name': 'Customer',
            'delivery_address': 'Address',
        }

    @staticmethod
    def get_help_for_screen_text():
        context = ScreenTextRenderer.get_context_example()
        screen_text = {field: '{{' + field + '}}' for field in context.keys()}
        rendered_text = ScreenTextRenderer(screen_text=screen_text).render(context=context)
        result = '\n'.join(['{{ ' + key + ' }} - ' + value for key, value in rendered_text.items()])

        return result
