from rest_framework import serializers

from base.api.legacy.serializers.fields import MarkdownField
from reporting.model_mapping import serializer_map
from tasks.models import ConcatenatedOrder, Order


class SkipEmptyNestedSerializerMixin(serializers.Serializer):

    def to_representation(self, instance):
        result = super().to_representation(instance)
        for field_name, field_type in self.fields.items():
            if isinstance(field_type, serializers.Serializer) and not result[field_name]:
                del result[field_name]
        return result


class SignaturePickUpConfirmationNestedSerializer(serializers.Serializer):
    url = serializers.CharField(required=False, source='pick_up_confirmation_signature')


class PickUpConfirmationNestedSerializer(SkipEmptyNestedSerializerMixin, serializers.Serializer):
    signature = SignaturePickUpConfirmationNestedSerializer(required=False, source='*')
    comment = serializers.CharField(required=False, source='pick_up_confirmation_comment')


class PickupWebOrderNestedSerializer(SkipEmptyNestedSerializerMixin, serializers.Serializer):
    customer_id = serializers.IntegerField(required=False, source='pickup')
    address_id = serializers.IntegerField(required=False, source='pickup_address')
    after = serializers.CharField(required=False, source='pickup_after')
    before = serializers.CharField(required=False, source='pickup_before')
    confirmation = PickUpConfirmationNestedSerializer(source='*')


class SignatureConfirmationNestedSerializer(serializers.Serializer):
    url = serializers.CharField(required=False, source='confirmation_signature')


class ConfirmationNestedSerializer(SkipEmptyNestedSerializerMixin, serializers.Serializer):
    signature = SignatureConfirmationNestedSerializer(source='*')
    comment = serializers.CharField(required=False, source='confirmation_comment')


class SignaturePreConfirmationNestedSerializer(serializers.Serializer):
    url = serializers.CharField(required=False, source='pre_confirmation_signature')


class PreConfirmationNestedSerializer(SkipEmptyNestedSerializerMixin, serializers.Serializer):
    signature = SignaturePreConfirmationNestedSerializer(source='*')
    comment = serializers.CharField(required=False, source='pre_confirmation_comment')


class DeliverWebOrderNestedSerializer(SkipEmptyNestedSerializerMixin, serializers.Serializer):
    customer_id = serializers.IntegerField(required=False, source='customer')
    address_id = serializers.IntegerField(required=False, source='deliver_address')
    after = serializers.CharField(required=False, source='deliver_after')
    before = serializers.CharField(required=False, source='deliver_before')
    pre_confirmation = PreConfirmationNestedSerializer(source='*')
    confirmation = ConfirmationNestedSerializer(source='*')


class WaybackWebOrderNestedSerializer(serializers.Serializer):
    point_id = serializers.IntegerField(required=False, source='wayback_point')
    hub_id = serializers.IntegerField(required=False, source='wayback_hub')


class TerminateCodesNestedSerializer(serializers.Serializer):
    codes = serializers.JSONField(required=False, source='completion_codes', )
    comment = serializers.CharField(required=False, source='terminate_comment')


class StatisticsWebOrderNestedSerializer(serializers.Serializer):
    created_at = serializers.CharField(required=False)
    updated_at = serializers.CharField(required=False)
    started_at = serializers.CharField(required=False)
    time_at_job = serializers.CharField(required=False)
    time_at_pickup = serializers.CharField(required=False)
    duration = serializers.CharField(required=False)
    pick_up_distance = serializers.IntegerField(required=False)
    wayback_distance = serializers.IntegerField(required=False)
    order_distance = serializers.IntegerField(required=False)


class GeofenceWebOrderNestedSerializer(serializers.Serializer):
    pickup_geofence_entered = serializers.BooleanField(required=False)
    time_inside_pickup_geofence = serializers.CharField(required=False)
    geofence_entered = serializers.BooleanField(required=False)
    geofence_entered_on_backend = serializers.BooleanField(required=False)
    time_inside_geofence = serializers.CharField(required=False)
    is_completed_by_geofence = serializers.BooleanField(required=False)


@serializer_map.register_converter_for_obj_dump(version='web', model_class=Order)
class DumpEventConverterOrderSerializer(SkipEmptyNestedSerializerMixin, serializers.Serializer):
    # convert json from OrderDeltaSerializer format to WebOrderSerializer format

    id = serializers.IntegerField(required=False)
    order_id = serializers.IntegerField(required=False)
    driver_id = serializers.IntegerField(required=False, source='driver')
    concatenated_order_id = serializers.IntegerField(required=False, source='concatenated_order')
    title = serializers.CharField(required=False)
    description = MarkdownField(required=False)
    comment = serializers.CharField(required=False)
    customer_comment = serializers.CharField(required=False)
    starting_point_id = serializers.IntegerField(required=False, source='starting_point')
    ending_point_id = serializers.IntegerField(required=False, source='ending_point')
    pickup = PickupWebOrderNestedSerializer(source='*')
    deliver = DeliverWebOrderNestedSerializer(source='*')
    wayback = WaybackWebOrderNestedSerializer(source='*')
    statistics = StatisticsWebOrderNestedSerializer(source='*')
    geofence = GeofenceWebOrderNestedSerializer(source='*')
    status = serializers.CharField(required=False)
    manager_id = serializers.IntegerField(required=False, source='manager')
    merchant_id = serializers.IntegerField(required=False, source='merchant')
    sub_branding_id = serializers.IntegerField(required=False, source='sub_branding')
    completion = TerminateCodesNestedSerializer(source='*')
    checklist_id = serializers.IntegerField(required=False, source='driver_checklist')
    label_ids = serializers.ListSerializer(child=serializers.IntegerField(), required=False, source='labels')
    skill_set_ids = serializers.ListSerializer(child=serializers.IntegerField(), required=False, source='skill_sets')
    barcodes = serializers.JSONField(required=False)
    cargoes = serializers.JSONField(required=False)
    is_confirmed_by_customer = serializers.BooleanField(required=False)
    customer_review_opt_in = serializers.BooleanField(required=False)
    capacity = serializers.FloatField(required=False)
    deleted = serializers.BooleanField(required=False)
    rating = serializers.IntegerField(required=False)
    cost = serializers.CharField(required=False)
    deadline_passed = serializers.BooleanField(required=False)
    changed_in_offline = serializers.BooleanField(required=False)
    external_job_id = serializers.IntegerField(required=False, source='external_job')
    model_prototype_id = serializers.IntegerField(required=False, source='model_prototype')
    customer_survey_id = serializers.IntegerField(required=False, source='customer_survey')


@serializer_map.register_converter_for_obj_dump(version='web', model_class=ConcatenatedOrder)
class DumpEventConverterConcatenatedOrderSerializer(DumpEventConverterOrderSerializer):
    order_ids = serializers.ListSerializer(child=serializers.IntegerField(), required=False)


__all__ = ['DumpEventConverterOrderSerializer', 'DumpEventConverterConcatenatedOrderSerializer']
