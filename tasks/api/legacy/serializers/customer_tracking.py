from rest_framework import serializers
from rest_framework.fields import SerializerMethodField

from driver.api.legacy.serializers.driver import DriverSerializer
from driver.api.legacy.serializers.location import DriverLocationSerializer
from merchant.api.legacy.serializers.merchants import CustomerGetBrandSerializer, MerchantSerializer
from tasks.models import Order

from .core import BaseOrderSerializer, OrderLocationSerializer


class CustomerMerchantSerializer(MerchantSerializer):
    class Meta(MerchantSerializer.Meta):
        fields = (
            'path_processing', 'use_pick_up_status', 'merchant_type',
            'pickup_failure_screen_text', 'feedback_redirect_enabled', 'show_company_name_for_customer',
            'round_corners_for_customer', 'customer_review_opt_in_enabled', 'customer_review_opt_in_text',
            'customer_review_screen_text', 'eta_with_traffic', 'language'
        )


class CustomerDriverLocationSerializer(DriverLocationSerializer):
    class Meta(DriverLocationSerializer.Meta):
        fields = ('id', 'location', 'improved_location', 'bearing')
        exclude = None


class CustomerDriverSerializer(DriverSerializer):
    last_location = CustomerDriverLocationSerializer(read_only=True)

    class Meta(DriverSerializer.Meta):
        fields = ('id', 'last_location', 'avatar', 'full_name', 'car')


class CustomerOrderSerializer(BaseOrderSerializer):
    driver = CustomerDriverSerializer(read_only=True)
    merchant = CustomerMerchantSerializer(read_only=True)
    deliver_address = OrderLocationSerializer(required=False)
    pickup_address = OrderLocationSerializer(required=False, allow_null=True)
    brand = SerializerMethodField()
    customer_survey_enabled = serializers.BooleanField()
    customer_survey_invite_text = SerializerMethodField()
    customer_survey_is_passed = SerializerMethodField()

    def __init__(self, *args, **kwargs):
        exclude_driver_fields = kwargs.get('exclude_driver_fields', None)
        if exclude_driver_fields:
            for f in kwargs.pop('exclude_driver_fields'):
                self.fields['driver'].fields.pop(f)
        super(CustomerOrderSerializer, self).__init__(*args, **kwargs)

    class Meta:
        model = Order
        fields = (
            'order_id', 'status', 'pickup_address', 'pickup_address_2', 'deliver_address', 'deliver_address_2',
            'is_confirmed_by_customer', 'customer_survey_is_passed', 'customer_survey_enabled',
            'updated_at', 'brand', 'customer_survey_invite_text',
            'driver', 'merchant',
            'customer_review_opt_in', 'rating', 'customer_comment',
        )
        editable_fields = {
            'is_confirmed_by_customer', 'status', 'customer_review_opt_in', 'rating', 'customer_comment',
        }
        read_only_fields = list(set(fields) - set(editable_fields))
        extra_kwargs = {
            'customer_review_opt_in': {'write_only': True},
            'rating': {'write_only': True},
            'customer_comment': {'write_only': True},
        }

    def get_brand(self, instance):
        brand_info = instance.sub_branding or instance.merchant
        obj = getattr(instance, instance.merchant.customer_tracking_phone_settings, None)
        phone = obj.phone if obj else ''
        store_url = instance.store_url or brand_info.store_url
        return CustomerGetBrandSerializer(brand_info, context={'phone': phone, 'store_url': store_url}).data

    def get_customer_survey_invite_text(self, instance):
        customer_survey_template = instance.customer_survey_template
        if customer_survey_template:
            return customer_survey_template.invite_text

    def get_customer_survey_is_passed(self, instance):
        if instance.customer_survey_id:
            return instance.customer_survey.is_passed
        return False

    def validate_customer_review_opt_in(self, attr):
        if self.instance and not self.instance.merchant.customer_review_opt_in_enabled:
            raise serializers.ValidationError('Customer review opt-in is disabled.')
        return attr

    def to_representation(self, instance):
        data = super().to_representation(instance)

        if instance.status == Order.NOT_ASSIGNED:
            if data['merchant']:
                del data['merchant']['eta_with_traffic']
            data.pop('driver', None)

        elif instance.status == Order.ASSIGNED:
            if data['merchant']:
                del data['merchant']['eta_with_traffic']
            if data['driver']:
                data['driver'].pop('last_location', None)
                data['driver'].pop('location', None)
                data['driver'].pop('car', None)

        elif instance.status in [Order.PICK_UP, Order.PICKED_UP, Order.IN_PROGRESS]:
            pass

        elif instance.status in [Order.WAY_BACK, Order.DELIVERED]:
            if data['merchant']:
                del data['merchant']['eta_with_traffic']
            data.pop('driver', None)
            data.pop('pickup_address', None)
            data.pop('pickup_address_2', None)
            data.pop('deliver_address', None)
            data.pop('deliver_address_2', None)

        elif instance.status == Order.FAILED:
            if data['merchant']:
                del data['merchant']['eta_with_traffic']
            if data['driver']:
                data['driver'].pop('last_location', None)
                data['driver'].pop('location', None)
                data['driver'].pop('car', None)

            if self.context.get('customer_type') == 'pickup':
                data.pop('deliver_address', None)
                data.pop('deliver_address_2', None)
            if self.context.get('customer_type') == 'deliver':
                data.pop('pickup_address', None)
                data.pop('pickup_address_2', None)

        return data


class CustomerOrderHistorySerializer(serializers.Serializer):
    new_value = serializers.CharField()
    happened_at = serializers.DateTimeField()
    event = serializers.SerializerMethodField()
    id = serializers.IntegerField()

    def get_event(self, instance):
        return instance.get_event_display()


class CustomerDriverLocationConverterSerializer(CustomerDriverLocationSerializer):
    timestamp = serializers.FloatField()


class CustomerOrderRouteSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False)
    path_before = serializers.JSONField(required=False)
    before = CustomerDriverLocationConverterSerializer(required=False)
    path = serializers.JSONField(required=False)
    now = CustomerDriverLocationConverterSerializer(required=False)


class CustomerOrderStatsSerializer(serializers.Serializer):
    order = CustomerOrderSerializer()
    history = CustomerOrderHistorySerializer(many=True, required=False)
    route = CustomerOrderRouteSerializer(required=False)
    message = serializers.JSONField(required=False)

    def to_representation(self, instance):
        order = instance['order']
        if order.status == Order.NOT_ASSIGNED:
            instance.pop('history', None)
        if order.status not in [Order.PICK_UP, Order.PICKED_UP, Order.IN_PROGRESS]:
            instance.pop('route', None)

        return super().to_representation(instance)
