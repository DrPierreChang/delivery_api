import copy
from collections import defaultdict
from operator import attrgetter

from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from base.models import Member
from merchant.models import Hub
from route_optimisation.const import HubOptions
from route_optimisation.utils.validation.fields import ManyMerchantsOptimisationPrimaryKeyRelatedField
from tasks.models import Order

from ...v1.serializers.options import ExternalOptionsOptimisationSerializer


class ExternalOptionsOptimisationSerializerV2(ExternalOptionsOptimisationSerializer):
    use_vehicle_capacity = serializers.BooleanField(required=False)

    def validate_use_vehicle_capacity(self, value):
        if value is True and self.context['merchant'].enable_job_capacity is False:
            raise serializers.ValidationError(
                'Vehicle Capacity feature is disabled, '
                'please turn this on to create {} that accounts Vehicle Capacity'.format(_('Optimisation'))
            )
        return value


class ManyMerchantsSeparateOptionsSerializer(serializers.Serializer):
    start_place = serializers.ChoiceField(choices=HubOptions.EXTERNAL_START_HUB, required=True)
    start_hub = ManyMerchantsOptimisationPrimaryKeyRelatedField(
        queryset=Hub.objects.all().select_related('merchant'), required=False, allow_null=True,
    )
    end_place = serializers.ChoiceField(choices=HubOptions.EXTERNAL_END_HUB, required=True)
    end_hub = ManyMerchantsOptimisationPrimaryKeyRelatedField(
        queryset=Hub.objects.all().select_related('merchant'), required=False, allow_null=True,
    )

    order_ids = ManyMerchantsOptimisationPrimaryKeyRelatedField(
        queryset=Order.objects.all().select_related('merchant'),
        lookup_field='order_id', required=False, many=True, raise_not_exist=True,
        pk_field=serializers.IntegerField(),
    )
    external_ids = ManyMerchantsOptimisationPrimaryKeyRelatedField(
        queryset=Order.objects.all().select_related('merchant', 'external_job',),
        lookup_field='external_job__external_id', required=False, many=True, raise_not_exist=True,
        pk_field=serializers.CharField(),
    )
    member_ids = ManyMerchantsOptimisationPrimaryKeyRelatedField(
        queryset=Member.drivers.all().select_related('merchant'),
        lookup_field='member_id', required=True, many=True, raise_not_exist=True,
        pk_field=serializers.IntegerField(),
    )

    working_hours = serializers.DictField(required=True)
    re_optimise_assigned = serializers.BooleanField(required=False)
    use_vehicle_capacity = serializers.BooleanField(required=False)
    service_time = serializers.IntegerField(required=False)

    def validate_member_ids(self, members):
        if not members:
            raise serializers.ValidationError('No drivers passed')
        return members

    def validate(self, attrs):
        attrs = super().validate(attrs)

        merchants = defaultdict(lambda: {'order_ids': [], 'external_ids': [], 'member_ids': [],
                                         'start_hub': None, 'end_hub': None})
        order_ids = attrs.pop('order_ids', [])
        for order in order_ids:
            merchants[order.merchant]['order_ids'].append(order)

        external_ids = attrs.pop('external_ids', [])
        for order in external_ids:
            merchants[order.merchant]['external_ids'].append(order)

        member_ids = attrs.pop('member_ids', [])
        for driver in member_ids:
            merchants[driver.current_merchant]['member_ids'].append(driver)

        start_hub = attrs.pop('start_hub', None)
        if start_hub:
            if len(merchants) > 1:
                raise serializers.ValidationError({'start_hub': 'You cannot set start hub for multiple merchants'})
            merchants[start_hub.merchant]['start_hub'] = start_hub

        end_hub = attrs.pop('end_hub', None)
        if end_hub:
            if len(merchants) > 1:
                raise serializers.ValidationError({'end_hub': 'You cannot set end hub for multiple merchants'})
            merchants[end_hub.merchant]['end_hub'] = end_hub

        result_attrs = []
        for merchant, merchant_fields in merchants.items():
            merchant_attrs = copy.deepcopy(attrs)
            merchant_attrs.update(merchant_fields)
            merchant_attrs['merchant'] = merchant
            result_attrs.append(merchant_attrs)
        return result_attrs

    def to_representation(self, validated_data):
        result = {}
        for options in validated_data:
            merchant = options.pop('merchant')
            result_options = super().to_representation(options)
            result_options['order_ids'] = list(map(attrgetter('order_id'), options['order_ids']))
            result_options['external_ids'] = list(map(attrgetter('external_job.external_id'), options['external_ids']))
            result_options['member_ids'] = list(map(attrgetter('member_id'), options['member_ids']))
            result[merchant] = result_options
        return result
