from django.core.management import BaseCommand
from django.template.loader import get_template

from notification.mixins import MessageTemplateStatus
from notification.models import MerchantMessageTemplate


class Command(BaseCommand):
    help = 'Use this command in case ' \
           'when you changed message template text ' \
           'and want to update it for existing merchants'

    def add_arguments(self, parser):
        parser.add_argument('template_type', type=int)
        parser.add_argument('merchant_id', nargs='*', type=int)

        parser.add_argument(
            '--delete',
            default=False,
            help='Delete message template instead of updating it',
        )

        parser.add_argument(
            '--sms',
            default=False,
            help='Update SMS message template',
        )

    def handle(self, *args, **options):
        template_type = options.get('template_type')
        delete = options.get('delete')
        sms = options.get('sms')
        merchant_ids = options.get('merchant_id')

        qs = MerchantMessageTemplate.objects.filter(template_type=template_type)

        if merchant_ids:
            qs = qs.filter(merchant_id__in=merchant_ids)

        if delete:
            _, _rows_count = qs.delete()
            if _rows_count:
                self.stdout.write(self.style.SUCCESS('Successfully deleted "{}" objects'.format(_rows_count)))
            else:
                self.stdout.write(self.style.WARNING('Nothing to delete'))
            return

        template_name = MessageTemplateStatus.template_names_map.get(template_type)
        if not template_name:
            self.stdout.write(self.style.ERROR('Template with type "{}" was not found.'.format(template_type)))
            return

        update_data = {
            'html_text': get_template(template_name + '.html').template.source,
            'subject': get_template(template_name + '.subject').template.source
        }

        if sms:
            update_data['text'] = get_template(template_name + '.txt').template.source

        _rows_count = qs.update(**update_data)

        if _rows_count:
            print(self.style)
            self.stdout.write(self.style.SUCCESS('Successfully updated "{}" objects'.format(_rows_count)))
        else:
            self.stdout.write(self.style.WARNING('Nothing to update'))
