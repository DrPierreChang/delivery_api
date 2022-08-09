from django.conf import settings

from rest_framework import serializers

from merchant.models import Merchant
from radaro_utils.serializers.mobile.fields import RadaroMobileCharField
from radaro_utils.serializers.mobile.serializers import RadaroMobileModelSerializer
from routing.serializers.fields import LatLngLocation

from .fields import MerchantDistanceChoiceField


class DriverBreakMerchantSerializer(RadaroMobileModelSerializer):
    interval = serializers.IntegerField(source='driver_break_interval')
    description = RadaroMobileCharField(source='driver_break_description')

    class Meta:
        model = Merchant
        fields = ('interval', 'description')

    def to_representation(self, value):
        if not value.driver_break_enabled:
            return None
        return super().to_representation(value)


class SignatureScreenTextMerchantSerializer(RadaroMobileModelSerializer):

    class Meta:
        model = Merchant
        fields = ('pre_inspection', 'delivery', 'pick_up', 'failure')
        extra_kwargs = {
            'pick_up': {'source': 'pickup_signature_screen_text'},
            'pre_inspection': {'source': 'pre_inspection_signature_screen_text'},
            'delivery': {'source': 'signature_screen_text'},
            'failure': {'source': 'job_failure_signature_screen_text'},
        }


class DefaultSkidSizesMerchantSerializer(serializers.ModelSerializer):
    width = serializers.FloatField(source='default_skid_width')
    height = serializers.FloatField(source='default_skid_height')
    length = serializers.FloatField(source='default_skid_length')

    class Meta:
        model = Merchant
        fields = ('width', 'height', 'length')


class DefaultSkidMerchantSerializer(serializers.ModelSerializer):
    sizes = DefaultSkidSizesMerchantSerializer(source='*')

    class Meta:
        model = Merchant
        fields = ('sizes',)


class MerchantSerializer(RadaroMobileModelSerializer):
    geofence_settings = serializers.SerializerMethodField()
    location = LatLngLocation()
    distance_show_in = MerchantDistanceChoiceField(Merchant.distances)
    signature_screen_text = SignatureScreenTextMerchantSerializer(source='*')
    take_a_break_dialogue = DriverBreakMerchantSerializer(source='*')
    default_skid = DefaultSkidMerchantSerializer(source='*', read_only=True)

    enable_pick_up_status = serializers.BooleanField(source='use_pick_up_status')
    enable_way_back_status = serializers.BooleanField(source='use_way_back_status')
    enable_subbranding = serializers.BooleanField(source='use_subbranding')
    enable_hubs = serializers.BooleanField(source='use_hubs')
    enable_job_checklist = serializers.SerializerMethodField()
    enable_sod_checklist = serializers.SerializerMethodField()
    enable_eod_checklist = serializers.SerializerMethodField()
    enable_driver_create_job = serializers.BooleanField(source='driver_can_create_job')
    enable_app_jobs_assignment = serializers.BooleanField(source='in_app_jobs_assignment')
    enable_address_2 = serializers.SerializerMethodField()
    enable_high_resolution = serializers.BooleanField(source='high_resolution')
    enable_eta_with_traffic = serializers.BooleanField(source='eta_with_traffic')

    class Meta:
        model = Merchant
        fields = ('id', 'merchant_identifier', 'geofence_settings', 'working_time',
                  'route_optimization', 'advanced_completion', 'option_barcodes', 'nti_ta_phone',

                  'location', 'distance_show_in', 'signature_screen_text', 'take_a_break_dialogue', 'default_skid',

                  'enable_pick_up_status', 'enable_way_back_status',
                  'enable_labels', 'enable_skill_sets', 'enable_subbranding', 'enable_hubs',

                  'enable_delivery_pre_confirmation', 'enable_delivery_confirmation', 'enable_pick_up_confirmation',
                  'enable_job_checklist', 'enable_sod_checklist', 'enable_eod_checklist', 'enable_job_capacity',
                  'enable_delivery_confirmation_documents', 'enable_reminder_to_attach_confirmation_documents',
                  'scanned_document_output_size',

                  'enable_driver_create_job', 'enable_auto_complete_customer_fields',  'enable_app_jobs_assignment',
                  'enable_address_2', 'enable_high_resolution', 'enable_eta_with_traffic', 'enable_skids',
                  'forbid_drivers_unassign_jobs', 'enable_concatenated_orders', 'forbid_drivers_edit_schedule')

    def get_enable_job_checklist(self, instance):
        return instance.checklist is not None

    def get_enable_sod_checklist(self, instance):
        return instance.sod_checklist is not None

    def get_enable_eod_checklist(self, instance):
        return instance.eod_checklist is not None

    def get_enable_address_2(self, instance):
        return settings.DELIVER_ADDRESS_2_ENABLED

    def get_geofence_settings(self, instance):
        choice = {
            Merchant.DISABLED: 'disabled',
            Merchant.UPON_ENTERING: 'upon_entering',
            Merchant.UPON_EXITING: 'upon_exiting',
        }
        return choice[instance.geofence_settings]
