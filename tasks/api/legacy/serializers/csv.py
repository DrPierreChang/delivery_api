import collections
import itertools as it_

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.fields import CharField

from base.api.legacy.serializers.fields import MemberIDDriverField
from base.models import Member
from merchant.api.legacy.serializers.fields import LabelPKField, ParseDateTimeTZField, SubBrandPKField
from merchant.api.legacy.serializers.skill_sets import OrderSkillSetsValidationMixin
from radaro_utils import helpers
from radaro_utils.radaro_phone.serializers import RadaroPhoneField
from radaro_utils.serializers.validators import LaterThenNowValidator
from tasks.api.legacy.serializers.mixins import ValidateJobIntervalsMixin
from tasks.mixins.order_status import OrderStatus
from tasks.models import Barcode, Order
from tasks.models.bulk import BulkDelayedUpload, OrderPrototype
from tasks.models.bulk_serializer_mapping import prototype_serializers
from webhooks.models import MerchantAPIKey

from .barcode import BarcodeField, BarcodeListSerializer
from .bulk import (
    OrderPrototypeChunkSerializer,
    OrderPrototypeListSerializer,
    OrderPrototypeSerializer,
    OrderRestoreSerializer,
)
from .core import OrderLocationSerializer
from .customers import CustomerSerializer, PickupSerializer
from .external_orders import ExternalJobSerializer
from .fields import StringAddressField
from .mixins import CustomerUnpackMixin, ExternalBarcodesUnpackMixin, PickupUnpackMixin


class SmallCSVDriverSerializer(serializers.ModelSerializer):
    class Meta:
        fields = ('first_name', 'member_id', 'last_name', 'full_name', 'phone', 'avatar')
        model = Member


class CSVOrderSerializer(ValidateJobIntervalsMixin, OrderSkillSetsValidationMixin, serializers.ModelSerializer):
    wrong_merchant_message_tpl = 'You don\'t have a {type} with this ID ({id}).'
    wrong_merchant_message_tpl_bulk = 'You don\'t have {type} with these IDs ({ids}).'

    customer_field_names = ('customer',)

    job_address = StringAddressField(allow_empty=False, required=True, source='deliver_address')
    job_address_2 = CharField(max_length=2048, required=False, allow_blank=True)
    pickup_address = StringAddressField(allow_empty=False, required=False)
    pickup_address_2 = CharField(max_length=2048, required=False, allow_blank=True)
    pickup_name = CharField(required=False, allow_blank=True, max_length=2048, source='pickup.name')
    pickup_email = serializers.EmailField(required=False, allow_blank=True, max_length=2048, source='pickup.email')
    pickup_phone = RadaroPhoneField(required=False, allow_blank=True, source='pickup.phone')
    job_name = CharField(max_length=2048, required=False, allow_blank=True)
    reference = CharField(source='title', max_length=2048, required=False, allow_blank=True)
    customer_name = CharField(required=True, max_length=2048, source='customer.name')
    customer_phone = RadaroPhoneField(required=False, allow_null=False, allow_blank=True, source='customer.phone')
    customer_email = serializers.EmailField(required=False, max_length=2048, source='customer.email', allow_blank=True)
    driver_id = MemberIDDriverField(required=False, allow_null=True)
    pickup_after = ParseDateTimeTZField(required=False, allow_null=True)
    pickup_deadline = ParseDateTimeTZField(required=False, allow_null=True, validators=[LaterThenNowValidator()],
                                           source='pickup_before')
    deliver_after = ParseDateTimeTZField(validators=[LaterThenNowValidator()], required=False, allow_null=True)
    job_deadline = ParseDateTimeTZField(default=None, validators=[LaterThenNowValidator()], source='deliver_before',
                                        allow_null=True)
    label_id = LabelPKField(required=False, allow_null=True)
    labels = LabelPKField(required=False, many=True)
    sub_brand_id = SubBrandPKField(required=False, allow_null=True, source='sub_branding_id')
    barcodes = BarcodeField(required=False)
    job_capacity = serializers.FloatField(source='capacity', min_value=0, required=False, allow_null=True)

    class Meta:
        fields = ('customer_name', 'job_address', 'job_address_2', 'pickup_address',
                  'pickup_address_2', 'pickup_name', 'pickup_email', 'pickup_phone',
                  'driver_id', 'pickup_after', 'pickup_deadline', 'deliver_after',
                  'job_deadline', 'comment', 'customer_email', 'customer_phone',
                  'job_name', 'labels', 'label_id', 'sub_brand_id', 'barcodes',
                  'skill_sets', 'job_capacity', 'reference')
        model = Order

    def validate(self, attrs):
        merchant = self.context['merchant']
        self._validate_job_intervals(attrs, merchant)

        if attrs.get('job_name') and not attrs.get('title'):
            attrs['title'] = attrs.pop('job_name')

        for address_field in ['deliver_address', 'pickup_address']:
            if attrs.get(address_field, False):
                loc = attrs[address_field]
                attrs[address_field] = OrderLocationSerializer(loc).data
                attrs['%s_id' % address_field] = loc.id

        job_capacity = attrs.get('capacity')
        if job_capacity and not merchant.enable_job_capacity:
            raise ValidationError(
                {'job_capacity': 'Job capacity option is disabled. Please, check your settings.'}
            )

        driver = attrs.get('driver_id', None)
        if driver:
            car_capacity = driver.car.capacity
            if job_capacity and car_capacity and job_capacity > car_capacity:
                raise ValidationError({'job_capacity': 'Forbidden to assign driver to job '
                                                       'since driver\'s car capacity is less than job capacity.'})
            attrs['driver'] = SmallCSVDriverSerializer(driver, context=self.context).data
        attrs['driver_id'] = driver.id if driver else None

        label = attrs.pop('label_id', None)
        if label and not attrs.get('labels'):
            attrs['labels'] = [label, ]

        skill_sets = attrs.get('skill_sets', [])
        self._validate_skill_sets_for_driver(skill_sets, driver)

        for m2m_attr in ('labels', 'skill_sets'):
            attrs[m2m_attr] = [obj.id for obj in attrs.get(m2m_attr, [])]

        return attrs

    def validate_skill_sets(self, skill_sets):
        merchant = self.context['merchant']
        invalid_skill_sets = [str(skill_set.id) for skill_set in skill_sets if merchant != skill_set.merchant]
        if invalid_skill_sets:
            message = self.wrong_merchant_message_tpl_bulk.format(type='skill_sets', ids=', '.join(invalid_skill_sets))
            raise ValidationError(message)
        return skill_sets

    def validate_label_id(self, label):
        merchant = self.context['merchant']
        if label and merchant != label.merchant:
            message = self.wrong_merchant_message_tpl.format(type='label_id', id=str(label.id))
            raise ValidationError(message)
        return label

    def validate_labels(self, labels):
        merchant = self.context['merchant']
        invalid_labels = [str(label.id) for label in labels if merchant != label.merchant]
        if invalid_labels:
            message = self.wrong_merchant_message_tpl_bulk.format(type='labels', ids=', '.join(invalid_labels))
            raise ValidationError(message)
        return labels

    def validate_driver_id(self, driver):
        merchant = self.context['merchant']
        if driver and (merchant != driver.current_merchant or not (driver.is_driver or driver.is_manager_or_driver)):
            raise ValidationError(self.wrong_merchant_message_tpl.format(type='driver', id=driver.member_id))
        return driver

    def validate_sub_brand_id(self, sub_brand):
        merchant = self.context['merchant']
        if sub_brand and merchant != sub_brand.merchant:
            raise ValidationError(self.wrong_merchant_message_tpl.format(type='sub_brand', id=sub_brand.id))
        return sub_brand.id if sub_brand else None

    def validate_barcodes(self, barcodes):
        existing_barcodes = self.context.get('existing_barcodes', set())

        new_barcodes = [barcode['code_data'] for barcode in barcodes if barcode.get('code_data', None)]

        merchant = self.context['merchant']
        existing_in_db_barcodes = Barcode.objects.merchant_active_barcodes(merchant).filter(code_data__in=new_barcodes)
        existing_in_db_barcodes = set(existing_in_db_barcodes.values_list('code_data', flat=True))
        existing_barcodes = existing_barcodes | existing_in_db_barcodes

        errors = []
        for new_barcode in new_barcodes:
            if new_barcode in existing_barcodes:
                errors.append('Barcode {} already exists.'.format(new_barcode))
            existing_barcodes.add(new_barcode)

        if errors:
            raise ValidationError(errors, code='non_unique_barcode')
        self.context['existing_barcodes'] = existing_barcodes
        return barcodes

    # Compatibility with previous versions api - errors should be nested
    def to_internal_value(self, data):
        try:
            self._set_merchant_context(data)
            res = super(CSVOrderSerializer, self).to_internal_value(data)
            return res
        except ValidationError as vex:
            fields = self.get_fields()
            err_dict = {}
            for f_name in vex.detail:
                attr_names = (getattr(fields[f_name], 'source') or f_name).split('.')
                if len(attr_names) > 1:
                    last_attr_name = attr_names.pop()
                    last_err = err_dict
                    for attr in attr_names:
                        nested_err = last_err.get(attr, {})
                        last_err[attr] = nested_err
                        last_err = nested_err
                    last_err[last_attr_name] = vex.detail[f_name]
                else:
                    err_dict[attr_names[0]] = vex.detail[f_name]
            vex.detail = err_dict
            raise vex

    def _set_merchant_context(self, data):
        auth = self.context['auth']
        merchant = auth.merchants.all() if (isinstance(auth, MerchantAPIKey) and auth.key_type == MerchantAPIKey.MULTI)\
            else self.context['user'].current_merchant

        if not isinstance(merchant, collections.Iterable):
            self.context['merchant'] = merchant
            return

        try:
            driver = self.fields['driver_id'].to_internal_value(data.get('driver_id'))
        except ValidationError as err:
            raise ValidationError({'driver_id': err.detail})
        if not driver:
            raise serializers.ValidationError({'driver_id': 'Driver is required for this order.'})
        if driver.current_merchant not in merchant:
            raise serializers.ValidationError({'driver_id': 'Invalid driver for this order'})
        self.context['merchant'] = driver.current_merchant


class CSVOrderUnpackSerializer(ExternalBarcodesUnpackMixin, CustomerUnpackMixin, PickupUnpackMixin,
                               serializers.ModelSerializer):
    deliver_address_id = serializers.IntegerField(source='deliver_address')
    pickup_address_id = serializers.IntegerField(source='pickup_address', required=False)
    customer = CustomerSerializer(allow_null=False, required=True)
    pickup = PickupSerializer(required=False)
    driver_id = serializers.IntegerField(required=False, allow_null=True)
    labels = LabelPKField(required=False, many=True)
    sub_branding_id = serializers.IntegerField(required=False, allow_null=True)
    barcodes = BarcodeListSerializer(required=False)

    def validate(self, attrs):
        attrs['deliver_address_id'] = attrs.pop('deliver_address')
        if 'pickup_address' in attrs:
            attrs['pickup_address_id'] = attrs.pop('pickup_address')
        self.unpack_fields(attrs)
        if attrs.get('driver_id', None):
            attrs['status'] = OrderStatus.ASSIGNED
        return attrs

    class Meta:
        model = Order
        fields = ('deliver_address_id', 'pickup_address_id', 'pickup', 'title', 'customer',
                  'driver_id', 'pickup_after', 'pickup_before', 'deliver_after',
                  'deliver_before', 'comment', 'labels', 'sub_branding_id', 'barcodes', 'skill_sets',
                  'capacity', 'merchant')
        extra_kwargs = {'merchant': {'required': False}}


@prototype_serializers.register(prototype_serializers.CSV)
class CSVOrderRestoreSerializer(OrderRestoreSerializer):
    child = CSVOrderUnpackSerializer()


class CSVOrderPrototypeSerializer(OrderPrototypeSerializer):
    external_job = ExternalJobSerializer(required=False)
    content = CSVOrderSerializer()

    def to_internal_value(self, data):
        m2m_relations = ['labels', 'skill_sets']

        for address, address_2 in (('job_address', 'job_address_2'), ('pickup_address', 'pickup_address_2')):
            if address in data:
                data[address] = (data[address], data.pop(address_2, ''))

        for rel in m2m_relations:
            if rel in data:
                data[rel] = data[rel].split(';') if data[rel] else []
        data = super(CSVOrderPrototypeSerializer, self).to_internal_value({'content': data})
        if data['content'].get('driver_id') and not getattr(self.parent.context['auth'], 'merchant', None):
            data['content']['merchant'] = Member.objects.get(pk=data['content']['driver_id']).current_merchant_id
        return data


class CSVOrderPrototypeListSerializer(OrderPrototypeListSerializer):
    child = CSVOrderPrototypeSerializer()


class CSVOrderPrototypeChunkSerializer(OrderPrototypeChunkSerializer):
    bulk_serializer_class = CSVOrderPrototypeListSerializer

    since = 0
    progress = 0
    user = None

    @property
    def context(self):
        base_context = super(CSVOrderPrototypeChunkSerializer, self).context
        return dict(base_context, user=self.user)

    def data_chunks(self, chunk_size, data_len):
        counter = 0
        for chunk in helpers.chunks(self.initial_data, chunk_size, length=data_len):
            self.progress = 100 * counter / data_len
            if self.progress > 100:
                self.progress = 100
            if self.since and not counter:
                yield it_.islice(chunk, self.since, chunk_size)
            else:
                yield chunk
            counter += chunk_size

    def validate_and_save(self, bulk, first_n=None, skip_n=0, *args, **kwargs):
        self.user = bulk.creator
        if first_n:
            for bulk_serializer in self.validate_in_chunks(chunk_size=first_n):
                bulk_serializer.save(bulk=bulk)
                break
        else:
            self.since = skip_n
            if len(self.initial_data) > self.since:
                for bulk_serializer in self.validate_in_chunks(line_since=self.since):
                    bulk_serializer.save(bulk=bulk)
                    bulk.event(self.progress, BulkDelayedUpload.PROGRESS)
            else:
                bulk.event(100, BulkDelayedUpload.PROGRESS)
        return bulk


class CSVOrderReportSerializer(serializers.ModelSerializer):
    order_title = serializers.CharField(source='title')
    external_job_id = serializers.CharField(source='external_job.external_id')
    order_status = serializers.CharField(source='status')
    deliver_address = serializers.CharField(source='deliver_address.address')
    deliver_address_2 = serializers.CharField(source='deliver_address.secondary_address')
    deliver_after_date = ParseDateTimeTZField(required=False, source='deliver_after_tz')
    deliver_before_date = ParseDateTimeTZField(required=False, validators=[LaterThenNowValidator()],
                                               source='deliver_before_tz')
    order_distance = serializers.FloatField(source='order_distance_calculated', allow_null=True)

    pickup_address = serializers.CharField(source='pickup_address.address')
    pickup_address_2 = serializers.CharField(source='pickup_address.secondary_address')
    pickup_name = serializers.CharField(source='pickup.name')
    pickup_email = serializers.CharField(source='pickup.email')
    pickup_phone = serializers.CharField(source='pickup.phone')
    pickup_after_date = ParseDateTimeTZField(required=False, source='pickup_after_tz')
    pickup_before_date = ParseDateTimeTZField(required=False, source='pickup_before_tz')
    pickup_geofence_entered_at = serializers.SerializerMethodField()
    time_at_pickup = serializers.DurationField(source='formatted_time_at_pickup')

    manager_name = serializers.CharField()
    manager_email = serializers.CharField(source='manager.email')
    manager_phone = serializers.CharField(source='manager.phone')
    manager_comment = serializers.CharField(source='comment')

    driver_id = serializers.IntegerField(source='driver_id', default=None)
    driver_name = serializers.CharField()
    driver_phone = serializers.CharField(source='driver.phone', default=None)
    member_id = serializers.IntegerField(source='driver.member_id', default=None)

    customer_name = serializers.CharField(source='customer.name')
    customer_email = serializers.CharField(source='customer.email')
    customer_phone = serializers.CharField(source='customer.phone')
    customer_rating = serializers.IntegerField(source='rating')

    created = ParseDateTimeTZField(read_only=True, source='created_at_tz')
    started = ParseDateTimeTZField(read_only=True, source='started_at_tz')
    completed_at = serializers.SerializerMethodField(read_only=True)
    time_at_job = serializers.DurationField(source='formatted_time_at_job')
    total_job_time = serializers.DurationField(source='formatted_duration')
    time_inside_geofence = serializers.DurationField(source='formatted_inside_geofence')
    geofence_entered_at = serializers.SerializerMethodField(read_only=True)

    labels = serializers.IntegerField(source='formatted_labels')
    label_names = serializers.CharField()
    skill_sets = serializers.IntegerField(source='formatted_skill_sets')
    skill_set_names = serializers.CharField()
    subbrand_name = serializers.CharField(source='sub_branding.name')
    full_report_url = serializers.CharField()

    completion_type = serializers.CharField(source='terminate_codes.type', default=None)
    completion_codes = serializers.CharField()
    completion_descriptions = serializers.CharField()
    completion_comment = serializers.CharField(source='terminate_comment')
    merchant_name = serializers.CharField(source='merchant.name')

    class Meta:
        model = Order
        fields = ('order_id', 'order_title', 'external_job_id', 'order_status', 'deliver_address', 'deliver_address_2',
                  'deliver_after_date', 'deliver_before_date', 'order_distance', 'description',
                  'manager_name', 'manager_email', 'manager_phone', 'manager_comment',
                  'driver_id', 'driver_name', 'driver_phone', 'member_id', 'confirmation_comment',
                  'customer_name', 'customer_email', 'customer_phone',
                  'customer_comment', 'customer_review_opt_in', 'customer_rating',
                  'created', 'started', 'completed_at', 'total_job_time', 'time_at_job', 'time_inside_geofence',
                  'geofence_entered_at',
                  'labels', 'label_names', 'skill_sets', 'skill_set_names', 'subbrand_name', 'full_report_url',
                  'completion_type', 'completion_codes', 'completion_descriptions', 'completion_comment',
                  'merchant_name', 'pickup_address', 'pickup_address_2', 'pickup_name', 'pickup_email',
                  'pickup_phone', 'pickup_before_date', 'pickup_geofence_entered_at', 'time_at_pickup',
                  'pickup_after_date'
                  )


class ExtendedCSVOrderReportSerializer(CSVOrderReportSerializer):
    survey_passed_at = ParseDateTimeTZField(read_only=True)

    class Meta(CSVOrderReportSerializer.Meta):
        model = Order
        fields = CSVOrderReportSerializer.Meta.fields + ('survey_passed_at',)


class OrderPrototypeErrorSerializer(serializers.ModelSerializer):
    index = serializers.IntegerField(source='line')
    data = serializers.JSONField(source='errors')

    class Meta:
        model = OrderPrototype
        fields = ('index', 'data')
