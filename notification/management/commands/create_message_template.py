from django.core.management import BaseCommand
from django.template.loader import get_template

from merchant.models import Merchant
from notification.mixins import MessageTemplateStatus
from notification.models import MerchantMessageTemplate


class Command(BaseCommand):
    help = 'Use this command in case ' \
           'when you want to create special ' \
           'message template text ' \
           'for existing merchants'

    def add_arguments(self, parser):
        parser.add_argument('template_type', type=int)
        parser.add_argument('merchant_id', nargs='*', type=int)
        parser.add_argument(
            '--no-html',
            default=False,
            help='Do not create HTML message and subject templates',
            type=bool,
        )

    def handle(self, *args, **options):
        template_type = options.get('template_type')
        merchant_ids = options.get('merchant_id')
        html = not options.get('no_html')

        merchants = Merchant.objects.all()
        if merchant_ids:
            merchants = merchants.filter(id__in=merchant_ids)

        template_name = MessageTemplateStatus.template_names_map.get(template_type)
        text = get_template(template_name + '.txt').template.source
        html_text, subject = '', ''
        if html:
            html_text = get_template(template_name + '.html').template.source
            subject = get_template(template_name + '.subject').template.source

        for merchant in merchants:
            MerchantMessageTemplate.objects.create(template_type=template_type, text=text, html_text=html_text,
                                                   subject=subject, enabled=False, merchant=merchant)
            self.stdout.write(self.style.SUCCESS('Successfully created for "{}"'.format(merchant.name)))
