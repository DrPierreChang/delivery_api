from __future__ import unicode_literals

from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.db.models import Field

from rest_framework import serializers

from constance import config

from merchant.models import Label, Merchant, MerchantGroup, SkillSet, SubBranding
from radaro_utils.middlewares.merchant import number_to_base64
from radaro_utils.radaro_phone.serializers import RadaroPhoneField
from radaro_utils.serializers.fields import Base64ImageField, TimezoneField
from radaro_utils.serializers.mixins import SerializerExcludeFieldsMixin
from radaro_utils.serializers.web.fields import WebPrimaryKeyWithMerchantRelatedField
from reporting.api.legacy.serializers.delta import DeltaSerializer
from reporting.model_mapping import serializer_map

from .fields import CustomChoiceField, LabelHexColorField


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


class MerchantSerializer(SerializerExcludeFieldsMixin, serializers.ModelSerializer):
    logo = Base64ImageField(allow_null=True)
    distance_show_in = CustomChoiceField(Merchant.distances)
    allow_confirmation = serializers.SerializerMethodField()
    checklist_enabled = serializers.SerializerMethodField()
    sod_checklist_enabled = serializers.SerializerMethodField()
    eod_checklist_enabled = serializers.SerializerMethodField()
    labels_colors = serializers.SerializerMethodField()
    use_success_codes = serializers.SerializerMethodField()
    phone = RadaroPhoneField(allow_blank=True)
    webhook_url = serializers.ListField(max_length=5, child=serializers.URLField())
    deliver_address_2_enabled = serializers.SerializerMethodField()
    driver_jobs_ordering = serializers.SerializerMethodField()
    enable_barcodes = serializers.SerializerMethodField()
    driver_break_interval = serializers.SerializerMethodField()
    has_related_surveys = serializers.BooleanField()
    default_skid = DefaultSkidMerchantSerializer(source='*', read_only=True)
    token = serializers.SerializerMethodField()
    required_skill_sets_for_notify_orders_ids = WebPrimaryKeyWithMerchantRelatedField(
        source='required_skill_sets_for_notify_orders', queryset=SkillSet.objects.all(), required=False, many=True,
    )

    class Meta:
        model = Merchant

        # Trick to include properties of model and not to enumerate all the fields, please
        _exclude = {'geofence_settings', 'timezone', 'sms_price', 'job_price', 'push_notifications_settings',
                    'pk', 'thumb_logo_100x100_field', 'sod_checklist', 'sod_checklist_email', 'customer_survey',
                    'instant_upcoming_delivery', 'instant_upcoming_delivery_enabled', 'eod_checklist',
                    'eod_checklist_email',
                    'default_skid_height', 'default_skid_length', 'default_skid_width', 'api_multi_key',
                    'required_skill_sets_for_notify_orders'}
        _include = {'allow_confirmation', 'labels_colors', 'checklist_enabled', 'sod_checklist_enabled',
                    'eod_checklist_enabled',
                    'use_success_codes', 'deliver_address_2_enabled', 'driver_jobs_ordering', 'has_related_surveys',
                    'enable_barcodes', 'default_skid', 'token', 'required_skill_sets_for_notify_orders_ids'}

        _properties = set(model.get_properties())
        _fields = {f.name for f in model._meta.get_fields()
                   if isinstance(f, Field) and not isinstance(f, GenericRelation)}
        fields = tuple((_fields | _include | _properties) - _exclude)
        read_only_fields = ('thumb_logo_100x100', 'balance', 'price_per_job', 'path_processing',
                            'price_per_sms', 'date_format', 'webhook_verification_token', 'nti_ta_phone',
                            'is_blocked', 'labels_colors', 'use_hubs', 'use_pick_up_status', 'use_way_back_status',
                            'use_success_codes', 'api_server_url', 'advanced_completion', 'high_resolution',
                            'signature_screen_text', 'pre_inspection_signature_screen_text',
                            'pickup_signature_screen_text', 'job_failure_signature_screen_text',
                            'job_failure_screen_text', 'merchant_identifier',
                            'eta_with_traffic', 'driver_jobs_ordering', 'driver_break_enabled',
                            'driver_break_description', 'round_corners_for_customer', 'has_related_surveys',
                            'pickup_failure_screen_text', 'enable_job_capacity', 'notify_of_not_assigned_orders',
                            'language')

    def validate_countries(self, countries):
        not_allowed_countries = list(set(countries) - set(config.ALLOWED_COUNTRIES))
        if not_allowed_countries:
            if len(not_allowed_countries) == 1:
                msg = 'Country (%s) is not allowed' % (list(not_allowed_countries)[0], )
            else:
                msg = 'Countries (%s) are not allowed' % (', '.join(not_allowed_countries))
            raise serializers.ValidationError(msg)
        return countries

    def get_allow_confirmation(self, instance):
        return instance.enable_delivery_confirmation

    def get_labels_colors(self, instance):
        return Label.get_versioned_colors_map(self.context['request'])

    def get_checklist_enabled(self, instance):
        return instance.checklist_id is not None

    def get_sod_checklist_enabled(self, instance):
        return instance.sod_checklist_id is not None

    def get_eod_checklist_enabled(self, instance):
        return instance.eod_checklist is not None

    def get_use_success_codes(self, instance):
        return instance.advanced_completion != Merchant.ADVANCED_COMPLETION_DISABLED

    def get_deliver_address_2_enabled(self, instance):
        return settings.DELIVER_ADDRESS_2_ENABLED

    def get_driver_jobs_ordering(self, instance):
        return 'time'

    def get_driver_break_interval(self, instance):
        return instance.driver_break_interval * 60 if instance.driver_break_interval else None

    def get_enable_barcodes(self, instance):
        return instance.option_barcodes != Merchant.TYPES_BARCODES.disable

    def get_token(self, instance):
        return number_to_base64(instance.id)


class SubBrandingSerializer(SerializerExcludeFieldsMixin, serializers.ModelSerializer):
    logo = Base64ImageField(allow_null=True, required=False)
    webhook_url = serializers.ListField(required=False, max_length=5, child=serializers.URLField())

    class Meta:
        model = SubBranding
        fields = '__all__'
        read_only_fields = ('merchant', )


@serializer_map.register_serializer
class SubBrandingDeltaSerializer(DeltaSerializer):
    class Meta(DeltaSerializer.Meta):
        model = SubBranding


class ExternalMerchantSerializer(MerchantSerializer):

    class Meta:
        model = MerchantSerializer.Meta.model
        fields = ('name', 'description', 'webhook_url', 'webhook_verification_token', 'logo', 'location',
                  'abn', 'address', 'phone', 'thumb_logo_100x100', 'api_server_url')
        read_only_fields = MerchantSerializer.Meta.read_only_fields


class MerchantGroupSerializer(serializers.ModelSerializer):
    merchants = ExternalMerchantSerializer(many=True, read_only=True, source='merchant_set')

    class Meta:
        model = MerchantGroup
        fields = '__all__'


@serializer_map.register_serializer_for_detailed_dump(version=1)
class LabelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Label
        fields = '__all__'
        read_only_fields = ('merchant',)

    def validate(self, attrs):
        request = self.context.get('request')
        color = attrs.get('color', self.instance.color if self.instance else Label.NO_COLOR)
        name = attrs.get('name', self.instance.name if self.instance else '')
        qs = request.user.current_merchant.label_set
        labels_limit = config.LABELS_LIMIT
        if qs.count() >= labels_limit:
            raise serializers.ValidationError('Too many labels. Limit is {}'.format(labels_limit))
        qs = qs.filter(color=color, name=name)
        qs = qs if not self.instance else qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError('Label with this name and color already exists')
        return attrs


@serializer_map.register_serializer
class LabelDeltaSerializer(DeltaSerializer):
    color = LabelHexColorField(required=False)

    class Meta(DeltaSerializer.Meta):
        model = Label


@serializer_map.register_serializer
class MerchantDeltaSerializer(DeltaSerializer):
    timezone = TimezoneField()

    class Meta(DeltaSerializer.Meta):
        model = Merchant


class ExternalLabelSerializer(LabelSerializer):
    class Meta:
        model = Label
        exclude = ('merchant', )


@serializer_map.register_serializer_for_detailed_dump(version='web')
@serializer_map.register_serializer_for_detailed_dump(version=2)
class LabelHexSerializer(LabelSerializer):
    color = LabelHexColorField(required=False)
    darkened_color = serializers.SerializerMethodField()

    class Meta:
        model = Label
        exclude = ('merchant', )

    def get_darkened_color(self, instance):
        return Label.DARKENED_COLOR_PAIRS[instance.color]


class CustomerGetBrandSerializer(serializers.Serializer):
    logo = Base64ImageField(allow_null=True, required=False)
    name = serializers.CharField(required=False, allow_blank=True)
    store_url = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    round_corners_for_customer = serializers.SerializerMethodField()

    def get_phone(self, instance):
        return self.context.get('phone', '')

    def get_round_corners_for_customer(self, instance):
        if hasattr(instance, 'round_corners_for_customer'):
            return instance.round_corners_for_customer
        return instance.merchant.round_corners_for_customer

    def get_store_url(self, instance):
        return self.context.get('store_url', instance.store_url)
