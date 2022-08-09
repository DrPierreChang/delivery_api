from __future__ import absolute_import, unicode_literals

import collections

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

import pytz

from base.api.legacy.serializers.fields import MarkdownField, MemberIDDriverField
from base.api.legacy.serializers.members import MerchantUserSerializer
from merchant.api.legacy.serializers.merchants import ExternalLabelSerializer
from merchant.models import Label
from merchant_extension.api.legacy.serializers.core import ExternalRetrieveResultChecklistSerializer
from radaro_utils.serializers.fields import Base64ImageField, ParseDateTimeField
from radaro_utils.serializers.mixins import SerializerExcludeFieldsMixin
from reporting.models import Event
from route_optimisation.models import RouteOptimisation
from tasks.api.legacy.serializers import CustomerUnpackMixin, OrderLocationSerializer, OrderSerializer
from tasks.api.legacy.serializers.bulk import OrderRestoreSerializer
from tasks.api.legacy.serializers.core import BaseOrderSerializer, OrderPreConfirmationPhotoSerializer
from tasks.api.legacy.serializers.customers import CustomerSerializer, PickupSerializer
from tasks.api.legacy.serializers.external_orders import ExternalJobSerializer
from tasks.api.legacy.serializers.mixins import (
    ExternalBarcodesUnpackMixin,
    ExternalSkidsUnpackMixin,
    OrderLocationUnpackMixin,
    PickupUnpackMixin,
)
from tasks.api.legacy.serializers.terminate_code import ExternalTerminateCodeSerializer
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order, OrderLocation
from tasks.models.bulk_serializer_mapping import prototype_serializers
from tasks.models.external import ExternalJob
from webhooks.models import MerchantAPIKey


class ExternalJobRelatedField(serializers.RelatedField):

    def to_representation(self, value):
        if isinstance(value, MerchantAPIKey):
            from webhooks.serializers import APIKeySerializer
            serializer = APIKeySerializer(value)
        else:
            raise Exception("Unexpected type")
        return serializer.data


class BulkExternalJobSerializer(serializers.ListSerializer):
    child = ExternalJobSerializer()

    def create(self, validated_data):
        jobs = [ExternalJob(**item) for item in validated_data]
        return ExternalJob.objects.bulk_create(jobs)

    def validate(self, attrs):
        jobs_set = set()
        for attr in attrs:
            external_id = attr['external_id']
            if external_id in jobs_set:
                raise ValidationError('External id {} in orders list is not unique.'.format(external_id))
            jobs_set.add(external_id)
        return attrs


class BulkExternalJobWithoutValidationSerializer(BulkExternalJobSerializer):
    child = ExternalJobSerializer(validate_extra=False)


class OrderFromExternalJobUnpackSerializer(ExternalBarcodesUnpackMixin,
                                           ExternalSkidsUnpackMixin,
                                           CustomerUnpackMixin,
                                           OrderLocationUnpackMixin,
                                           PickupUnpackMixin,
                                           BaseOrderSerializer):
    location_class = OrderLocation
    location_names = ('pickup_address', 'deliver_address', 'starting_point', 'ending_point')

    customer = CustomerSerializer()
    deliver_address = OrderLocationSerializer()
    pickup_address = OrderLocationSerializer(required=False, allow_null=True)
    pickup = PickupSerializer(required=False)
    starting_point = OrderLocationSerializer(required=False)
    ending_point = OrderLocationSerializer(required=False)
    description = MarkdownField(allow_blank=True, allow_null=True, required=False)

    # While validating during restore process we should get or create Customer and Location
    def validate(self, attrs):
        attrs = super(OrderFromExternalJobUnpackSerializer, self).validate(attrs)
        self.unpack_fields(attrs)
        if attrs.get('driver', None):
            attrs['status'] = OrderStatus.ASSIGNED
        return attrs

    class Meta:
        model = Order
        fields = ('driver', 'customer', 'comment', 'title', 'labels', 'deliver_address', 'deliver_address_2',
                  'pickup_address', 'pickup_address_2', 'pickup', 'pickup_after', 'pickup_before', 'starting_point',
                  'ending_point', 'description', 'terminate_code', 'error_code', 'error_comment', 'deliver_after',
                  'deliver_before', 'sub_branding', 'skill_sets', 'barcodes', 'cargoes', 'capacity', 'merchant',
                  'enable_rating_reminder', 'store_url')
        extra_kwargs = {'merchant': {'required': False}}


@prototype_serializers.register(prototype_serializers.EXTERNAL)
class ExternalJobRestoreSerializer(OrderRestoreSerializer):
    child = OrderFromExternalJobUnpackSerializer()


class ExternalLabelField(serializers.PrimaryKeyRelatedField):
    def __init__(self, pk_field_serializer, **kwargs):
        self.pk_field_serializer = pk_field_serializer
        super(ExternalLabelField, self).__init__(**kwargs)

    def use_pk_only_optimization(self):
        return False

    def to_internal_value(self, data):
        if isinstance(data, dict):
            if self.pk_field is not None:
                data = self.pk_field_serializer(context=self.context).to_internal_value(data)
            request = self.context.get('request', None)
            merchant = request.user.current_merchant
            obj, _ = self.queryset.get_or_create(merchant=merchant, **data)
            return obj

        try:
            return self.get_queryset().get(pk=data)
        except ObjectDoesNotExist:
            self.fail('does_not_exist', pk_value=data)
        except (TypeError, ValueError):
            self.fail('incorrect_type', data_type=type(data).__name__)


class OrderFromExternalJobSerializer(SerializerExcludeFieldsMixin, OrderSerializer):
    geofence_entered_at = ParseDateTimeField(read_only=True)
    geofence_exited_at = ParseDateTimeField(read_only=True)
    pickup_geofence_entered_at = ParseDateTimeField(read_only=True)
    pickup_geofence_exited_at = ParseDateTimeField(read_only=True)
    duration = serializers.DurationField(read_only=True)
    driver = MemberIDDriverField(required=False)
    external_id = serializers.SerializerMethodField(read_only=True)
    manager = MerchantUserSerializer(exclude_fields=OrderSerializer.exclude_manager_fields, read_only=True)
    driver_checklist = ExternalRetrieveResultChecklistSerializer(read_only=True)
    customer_tracking_url = serializers.SerializerMethodField(read_only=True)
    completed_at = serializers.DateTimeField(source='finished_at', read_only=True)
    completion_code = ExternalTerminateCodeSerializer(read_only=True, source='terminate_code')
    completion_codes = ExternalTerminateCodeSerializer(read_only=True, many=True, source='terminate_codes')
    completion_comment = serializers.CharField(source='terminate_comment', read_only=True)
    pre_inspection_photos = OrderPreConfirmationPhotoSerializer(many=True, read_only=True,
                                                                source='pre_confirmation_photos')
    pre_inspection_signature = Base64ImageField(read_only=True, source='pre_confirmation_signature')
    pre_inspection_comment = serializers.CharField(read_only=True, source='pre_confirmation_comment')
    label = ExternalLabelField(queryset=Label.objects, pk_field_serializer=ExternalLabelSerializer,
                               allow_null=True, required=False)
    labels = ExternalLabelField(queryset=Label.objects, pk_field_serializer=ExternalLabelSerializer,
                                many=True, required=False)
    delivery_interval = serializers.SerializerMethodField()
    optimisation_id = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ('external_id', 'deliver_after', 'deliver_before', 'delivery_interval', 'manager', 'customer',
                  'deliver_address', 'deliver_address_2', 'pickup_address', 'pickup_address_2',
                  'pickup', 'pickup_after', 'pickup_before', 'confirmation_signature', 'geofence_entered_at',
                  'geofence_exited_at', 'title', 'comment', 'started_at', 'picked_up_at', 'pick_up_distance',
                  'order_distance', 'status', 'order_id', 'starting_point', 'confirmation_comment',
                  'updated_at', 'created_at', 'rating', 'customer_comment', 'customer_review_opt_in',
                  'duration', 'deadline_passed', 'driver', 'merchant', 'description', 'sub_branding', 'label', 'labels',
                  'error_code', 'error_comment', 'completion_code', 'completion_codes', 'completion_comment',
                  'customer_tracking_url', 'is_confirmed_by_customer', 'order_confirmation_photos',
                  'order_confirmation_documents', 'pre_inspection_comment',
                  'pre_inspection_signature', 'pre_inspection_photos', 'driver_checklist',
                  'pre_confirmation_photos', 'pre_confirmation_signature', 'pre_confirmation_comment',
                  'skill_sets', 'barcodes', 'wayback_point', 'wayback_hub', 'completed_at',
                  'pickup_geofence_entered_at',
                  'pickup_geofence_exited_at', 'pick_up_confirmation_photos', 'pick_up_confirmation_signature',
                  'pick_up_confirmation_comment', 'cargoes', 'capacity', 'public_report_link', 'optimisation_id',
                  'enable_rating_reminder', 'custom_redirect_url')

        read_only_fields = ('order_id', 'merchant', 'duration', 'started_at', 'created_at',
                            'picked_up_at', 'pick_up_distance', 'wayback_point', 'wayback_hub',
                            'rating', 'customer_comment', 'confirmation_comment',
                            'order_confirmation_photos', 'pre_confirmation_comment',
                            'pre_confirmation_signature', 'pre_confirmation_photos',
                            'pre_inspection_signature', 'pre_inspection_photos',
                            'customer_review_opt_in', 'deadline_passed', 'pick_up_confirmation_photos',
                            'pick_up_confirmation_signature', 'pick_up_confirmation_comment', 'optimisation_id')
        extra_kwargs = {'custom_redirect_url': {'source': 'store_url'}}

    @property
    def _user(self):
        return self.context.get('user', self.context.get('request').user)

    def __init__(self, *args,  **kwargs):
        if args and isinstance(args[0], list) and len(args[0]):
            self.events = Event.objects\
                .pick_related_dates(related_fields=('geofence_entered', 'pickup_geofence_entered'),
                                    related_values=(True, False), objects=args[0])
        super(OrderFromExternalJobSerializer, self).__init__(*args, **kwargs)

    def to_representation(self, instance):
        model_attributes = {
            'geofence_entered_at': None, 'geofence_exited_at': None,
            'pickup_geofence_entered_at': None, 'pickup_geofence_exited_at': None
        }
        stats = getattr(self, 'events', None)
        if stats is None:
            stats = Event.objects.pick_related_dates(
                related_fields=('geofence_entered',),
                related_values=(True, False),
                objects=(instance,)
            )
        if stats:
            events = stats.get(instance.id, None)
            if events:
                model_attributes['geofence_entered_at'] = events.get('geofence_entered', {}).get('True')
                model_attributes['geofence_exited_at'] = events.get('geofence_entered', {}).get('False')
                model_attributes['pickup_geofence_entered_at'] = events.get('pickup_geofence_entered', {}).get('True')
                model_attributes['pickup_geofence_exited_at'] = events.get('pickup_geofence_entered', {}).get('False')
        for field, val in model_attributes.items():
            setattr(instance, field, val)
        return super(OrderFromExternalJobSerializer, self).to_representation(instance)

    def get_external_id(self, instance):
        return instance.external_job.external_id if instance.external_job else None

    def get_customer_tracking_url(self, instance):
        return instance.get_order_url() if instance.show_customer_tracking_page() else ''

    def get_delivery_interval(self, instance):
        # for backward compatibility
        default_bounds = '[)'

        if not (instance.deliver_after and instance.deliver_before):
            return None

        upper, lower = map(lambda dt: dt.astimezone(pytz.timezone(settings.TIME_ZONE)).isoformat(),
                           (instance.deliver_before, instance.deliver_after))
        up, low = map(lambda dt: dt[:-6] + 'Z' if dt.endswith('+00:00') else dt, (upper, lower))

        return {'upper': up, 'lower': low, 'bounds': default_bounds}

    def get_optimisation_id(self, order):
        ro_route_point = order.route_points.last()
        active_states = (RouteOptimisation.STATE.COMPLETED, RouteOptimisation.STATE.RUNNING,
                         RouteOptimisation.STATE.FINISHED)
        if ro_route_point and ro_route_point.route.optimisation.state in active_states:
            return ro_route_point.route.optimisation_id

    def _get_order_merchant(self, attrs):
        return self.context['merchant']

    def _set_merchant_context(self, data):
        request = self.context['request']
        merchant = request.auth.merchants.all() if (isinstance(request.auth, MerchantAPIKey)
                                                    and request.auth.key_type == MerchantAPIKey.MULTI) \
            else request.user.current_merchant

        if not isinstance(merchant, collections.Iterable):
            self.context['merchant'] = merchant
            return

        if not self.instance:
            try:
                driver = self.fields['driver'].to_internal_value(data.get('driver'))
            except ValidationError as err:
                raise ValidationError({'driver': err.detail})
            if not driver:
                raise serializers.ValidationError({'driver': 'Driver is required for this order.'})
            if driver.current_merchant not in merchant:
                raise serializers.ValidationError({'driver': 'Invalid driver for this order'})
            merchant = driver.current_merchant
        else:
            merchant = self.instance.merchant
        self.context['merchant'] = merchant

    def to_internal_value(self, data):
        self._set_merchant_context(data)
        return super().to_internal_value(data)

    def validate_status_with_driver(self, attrs):
        driver = attrs.get('driver', None)
        current_status = getattr(self.instance, 'status', None)
        new_status = attrs.get('status', None)
        statuses_set = {current_status} if not new_status else {current_status, new_status}
        can_edit = set(OrderStatus._can_edit_job_statuses).issuperset(statuses_set)

        if self.instance and not can_edit:
            used_fields = set(attrs.keys())

            if used_fields - {'status', 'skids'}:
                error_msg = 'Forbidden to change job details in status "{status}"'.format(
                        status=new_status or current_status
                    )
                raise ValidationError(error_msg)

            _can_edit_skids_statuses = {OrderStatus.NOT_ASSIGNED, OrderStatus.ASSIGNED, OrderStatus.IN_PROGRESS}
            if 'skids' in used_fields and not _can_edit_skids_statuses.issuperset(statuses_set):
                error_msg = 'Forbidden to change job skids in status "{status}"'.format(
                    status=new_status or current_status
                )
                raise ValidationError(error_msg)

        if new_status:
            # used self.instance if we update object and attrs if we create it.
            set_value = (lambda k, v: setattr(self.instance, k, v)) if self.instance \
                else (lambda k, v: attrs.update({k: v}))

            assign_driver_to_order = new_status == Order.ASSIGNED
            unassigned_driver_from_order = new_status == Order.NOT_ASSIGNED

            if assign_driver_to_order and not driver:
                raise ValidationError({'driver': ['Job can\'t be assigned without driver.', ]})
            if unassigned_driver_from_order and driver:
                raise ValidationError({'driver': ['Job can\'t be unassigned with driver.', ]})
            if assign_driver_to_order or unassigned_driver_from_order:
                set_value('driver', driver)

        elif driver and current_status == OrderStatus.NOT_ASSIGNED:
            attrs['status'] = Order.ASSIGNED
        elif 'driver' in attrs and driver is None:
            attrs['status'] = OrderStatus.NOT_ASSIGNED
        return attrs

    def validate(self, attrs):
        self.validate_status_with_driver(attrs)
        attrs = super(OrderFromExternalJobSerializer, self).validate(attrs)

        labels = attrs.get('labels', self.instance.labels.all() if self.instance else [])
        attrs['labels'] = [label.id for label in labels]

        for primary_related in ['sub_branding']:
            obj = attrs.get(primary_related, getattr(self.instance, primary_related) if self.instance else None)
            attrs[primary_related] = getattr(obj, 'pk', None)

        return attrs

    def save(self, **kwargs):
        for primary_related in ['sub_branding']:
            obj_id = self.validated_data.get(primary_related, None)
            if obj_id:
                self.validated_data['%s_id' % primary_related] = obj_id
                del self.validated_data[primary_related]
        return super(OrderFromExternalJobSerializer, self).save(**kwargs)


class EventTypeChoiceField(serializers.ChoiceField):

    def to_representation(self, value):
        return self.choices.get(value)


class ExternalJobEventsSerializer(serializers.Serializer):
    DELETED = -1
    CREATED = 0
    UPDATED = 2

    events = (
        (DELETED, 'deleted'),
        (CREATED, 'created'),
        (UPDATED, 'updated'),
    )
    new_values = serializers.DictField()
    old_values = serializers.DictField()
    order_info = OrderFromExternalJobSerializer(exclude_fields=('order_confirmation_documents',))
    updated_at = serializers.DateTimeField()
    event_type = EventTypeChoiceField(choices=events)
    token = serializers.CharField(max_length=255)
    topic = serializers.CharField(max_length=128)


__all__ = ['BulkExternalJobSerializer', 'OrderFromExternalJobSerializer', 'ExternalJobRelatedField',
           'ExternalJobEventsSerializer']
