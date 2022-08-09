from django.conf import settings
from django.core.management import BaseCommand

import boto

from documents.models import OrderConfirmationDocument
from merchant.models import Merchant
from merchant_extension.models import Checklist, ResultChecklist
from notification.models import TemplateEmailAttachment
from radaro_utils import helpers
from reporting.models import ExportReportInstance
from tasks.models import Order, OrderConfirmationPhoto, OrderPickUpConfirmationPhoto, OrderPreConfirmationPhoto
from tasks.models.bulk import CSVOrdersFile

CHUNK_SIZE = 1000


class Command(BaseCommand):
    help = "Copy moved merchant's media from source to current cluster-related s3 'folder'." \
           "Intended for use as a part of merchant transfer between clusters."

    def add_arguments(self, parser):
        parser.add_argument('merchant_id', type=int)
        parser.add_argument('source_cluster_number', type=int, default=settings.CLUSTER_NUMBER[1:])
        parser.add_argument(
            '--delete',
            default=False,
            help='Delete media for specified merchant',
        )

    def handle(self, *args, **options):
        merchant_id = options.get('merchant_id')
        cluster_number = options.get('source_cluster_number')
        delete = options.get('delete')

        order_values = Order.objects.filter(merchant_id=merchant_id)\
            .values('id', 'confirmation_signature', 'pre_confirmation_signature', 'pick_up_confirmation_signature',
                    'customer_survey_id', 'driver_checklist_id')
        order_ids = list(map(lambda d: d.pop('id'), order_values))
        result_checklist_ids = list(filter(lambda pk: bool(pk),
                                           map(lambda d: d.pop('customer_survey_id'), order_values))) \
            + list(filter(lambda pk: bool(pk), map(lambda d: d.pop('driver_checklist_id'), order_values)))

        order_images = [image for values in order_values for image in values.values() if image]
        docs = list(OrderConfirmationDocument.objects.filter(order_id__in=order_ids).values_list('document', flat=True))

        confirmation_image_models = (OrderConfirmationPhoto, OrderPreConfirmationPhoto, OrderPickUpConfirmationPhoto)
        confirmation_images = [image for model in confirmation_image_models
                               for image in model.objects.filter(order_id__in=order_ids).values_list('image', flat=True)]

        logo_images = list(set(logo for res in Merchant.objects.filter(id=merchant_id)
                               .values_list('logo', 'thumb_logo_100x100_field', 'subbrandings__logo', 'member__avatar',
                                            'member__thumb_avatar_100x100_field') for logo in res if logo))

        checklist_ids = list(set(checklist_id for res in Merchant.objects.filter(id=merchant_id)
                                 .values_list('checklist_id', 'sod_checklist_id', 'eod_checklist_id',
                                              'customer_survey_id', 'subbrandings__customer_survey_id')
                                 for checklist_id in res if checklist_id)
                             | set(ResultChecklist.objects.filter(id__in=result_checklist_ids)
                                   .values_list('checklist_id', flat=True).distinct()))
        question_images = [image for res in Checklist.objects.filter(id__in=checklist_ids)
                           .values_list('sections__questions__description_image') for image in res if image]
        result_checklist_images = list(set(image for res in ResultChecklist.objects.filter(id__in=result_checklist_ids)
                                           .values_list('confirmation_signature', 'confirmation_photos__image',
                                                        'result_answers__photos__image')
                                           for image in res if image))

        files = list(ExportReportInstance.objects.filter(merchant_id=merchant_id).values_list('file', flat=True))\
            + list(CSVOrdersFile.objects.filter(bulk__merchant_id=merchant_id).values_list('file', flat=True))\
            + list(TemplateEmailAttachment.objects.filter(email_message__template__merchant_id=merchant_id)
                   .values_list('file', flat=True))

        file_names = order_images + docs + confirmation_images + logo_images + question_images \
            + result_checklist_images + files
        file_names_count = len(file_names)
        print('total count: {}'.format(file_names_count))

        s3 = boto.connect_s3(settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_ACCESS_KEY)
        bucket = s3.get_bucket(settings.AWS_STORAGE_BUCKET_NAME)

        source_media_folder = '{}{}'.format(settings.MEDIA_FOLDER.split('-')[0],
                                            '-%s' % cluster_number if cluster_number > 1 else '')
        if delete:
            for file_chunk in helpers.chunks(file_names, CHUNK_SIZE, file_names_count):
                for file_name in file_chunk:
                    bucket.delete_key('{0}/{1}'.format(source_media_folder, file_name))
                print('processed {} files'.format(len(file_chunk)))
        else:
            for file_chunk in helpers.chunks(file_names, CHUNK_SIZE, file_names_count):
                for file_name in file_chunk:
                    bucket.copy_key('{0}/{1}'.format(settings.MEDIA_FOLDER, file_name),
                                    settings.AWS_STORAGE_BUCKET_NAME,
                                    '{0}/{1}'.format(source_media_folder, file_name),
                                    preserve_acl=True)
                print('processed {} files'.format(len(file_chunk)))
