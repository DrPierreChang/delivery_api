from django.conf import settings
from django.db import transaction

from delivery.celery import app
from radaro_utils.radaro_csv.exceptions import MissingRequiredHeadersException
from tasks.api.legacy.serializers.csv import CSVOrderPrototypeChunkSerializer
from tasks.celery_tasks import bulk__create_jobs
from tasks.csv_parsing import OrderCSVParser, _messages
from tasks.models import BulkDelayedUpload


@app.task()
def confirm_bulk_upload_v2(bulk_id):
    bulk = BulkDelayedUpload.objects.get(id=bulk_id)
    try:
        with transaction.atomic():
            bulk__create_jobs(bulk, async_=False, set_confirmation=False)
            msg = '{} {}: {}.'.format(_messages['saving_finished'], _messages['saved_amount'], bulk.state_params['saved'])
            bulk.confirm()
            bulk.event(msg, BulkDelayedUpload.INFO, force_save=True)
    except Exception as ex:
        bulk.fail()
        bulk.event(_messages['critical'], BulkDelayedUpload.ERROR, force_save=True)


class CSVParserTask(object):
    messages = _messages

    parser = None
    serializer = None

    parser_class = OrderCSVParser
    serializer_class = CSVOrderPrototypeChunkSerializer

    def __init__(self, bulk, source):
        self.preview_length = settings.CSV_UPLOAD_PREVIEW_AMOUNT
        self.bulk = bulk
        self.source = source
        self.prepare()

    def prepare(self):
        try:
            self.parser = self.parser_class(self.bulk.csv_file)
            if self.bulk.merchant and len(self.parser) * self.bulk.merchant.price_per_job > self.bulk.merchant.balance:
                return self.finish(_messages['low_balance'], success=False)
            self.serializer = self.serializer_class(data=self.parser, context={'auth': self.source})
        except MissingRequiredHeadersException as mrhex:
            error_message = _messages['required_fields'] + ' Missing columns: ' + ', '.join(mrhex.fields)
            self.finish(error_message, success=False)

    def finish(self, message, success=True):
        if self.parser:
            self.parser.finish()
        if success:
            self.bulk.complete()
            self.bulk.event(message, BulkDelayedUpload.INFO)
        else:
            self.bulk.fail()
            self.bulk.event(message, BulkDelayedUpload.ERROR)
        self.bulk.save()
        return self.bulk

    def generate_preview(self):
        self.bulk.begin()
        optional_missing = self.parser.mapper.optional_missing - self.skip_warn_optional_missing
        if optional_missing:
            _message = _messages['optional_skipped'] + ' Columns: ' + ', '.join(optional_missing)
            self.bulk.event(_message, BulkDelayedUpload.WARNING)
        if self.parser.mapper.unknown_columns:
            _message = _messages['unknown_columns'] + ' Columns: ' + ', '.join(self.parser.mapper.unknown_columns)
            self.bulk.event(_message, BulkDelayedUpload.WARNING)
        self.serializer.is_valid(raise_exception=False)
        self.bulk = self.serializer.validate_and_save(self.bulk, first_n=self.preview_length)
        self.bulk.check_errors_and_next_state()
        if self.bulk.is_in(BulkDelayedUpload.FAILED):
            self.bulk.event(_messages['preview_errors'], BulkDelayedUpload.ERROR)
        elif self.bulk.is_in(BulkDelayedUpload.READY):
            self.bulk.event(_messages['preview_finished'], BulkDelayedUpload.INFO)
        self.bulk.save()
        return self.bulk

    def run_parsing(self):
        self.bulk.continues()
        self.bulk.event(_messages['continued'], BulkDelayedUpload.INFO, force_save=True)
        self.bulk = self.serializer.validate_and_save(self.bulk, skip_n=self.preview_length)
        self.bulk.update_state()
        _message = '{} {}: {}.'.format(_messages['finished'], _messages['processed_amount'],
                                       self.bulk.state_params['processed'])
        self.finish(_message, success=True)

    @property
    def skip_warn_optional_missing(self):
        merchant = self.bulk.merchant
        fields = {'job_name'}
        if not merchant.use_subbranding:
            fields.add('sub_brand_id')
        if not merchant.enable_labels:
            fields |= {'labels', 'label_id'}
        else:
            fields.add('label_id')
        if merchant.option_barcodes == merchant.TYPES_BARCODES.disable:
            fields.add('barcodes')
        if not merchant.enable_skill_sets:
            fields.add('skill_sets')
        if not merchant.use_pick_up_status:
            fields |= {'pickup_address', 'pickup_address_2',
                       'pickup_name', 'pickup_email', 'pickup_phone'}
        if not merchant.enable_job_capacity:
            fields.add('job_capacity')
        return fields


@app.task()
def generate_orders_from_csv_v2(bulk_id, source, preview_length=None):
    csv_task = None
    bulk = BulkDelayedUpload.objects.select_related('creator', 'csv_file', 'merchant').get(id=bulk_id)
    try:
        bulk.is_possible(raise_exception=True)
        csv_task = CSVParserTask(bulk, source)
        if preview_length is not None:
            csv_task.preview_length = preview_length
        csv_task.run_parsing()
    except Exception:
        if csv_task:
            error_message = _messages['critical']
            csv_task.finish(error_message, success=False)
        raise
