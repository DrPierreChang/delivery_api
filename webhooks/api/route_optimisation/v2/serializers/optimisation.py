import copy

from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from route_optimisation.models import OptimisationTask, RouteOptimisation

from ...v1.serializers.optimisation import ExternalRouteOptimisationSerializerBase
from .fields import ContextMerchantDefault, ExternalSourceIDDefault, ExternalSourceTypeDefault
from .options import ExternalOptionsOptimisationSerializerV2, ManyMerchantsSeparateOptionsSerializer


class ReadExternalRouteOptimisationSerializer(ExternalRouteOptimisationSerializerBase):
    merchant = serializers.PrimaryKeyRelatedField(read_only=True)


class ExternalRouteOptimisationSerializer(ExternalRouteOptimisationSerializerBase):
    merchant = serializers.HiddenField(default=ContextMerchantDefault(), write_only=True)
    external_source_id = serializers.HiddenField(default=ExternalSourceIDDefault(), write_only=True)
    external_source_type_id = serializers.HiddenField(default=ExternalSourceTypeDefault(), write_only=True)

    class Meta(ExternalRouteOptimisationSerializerBase.Meta):
        fields = ExternalRouteOptimisationSerializerBase.Meta.fields + (
            'external_source_id', 'external_source_type_id',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._merchant = None

    def to_internal_value(self, data):
        self._merchant = data.get('merchant')
        data = super().to_internal_value(data)
        self._merchant = None
        return data

    @property
    def context(self):
        ctx = super().context
        if self._merchant:
            ctx['merchant'] = self._merchant
        return ctx

    def validate_day(self, value):
        if value < timezone.now().astimezone(self._merchant.timezone).date():
            raise serializers.ValidationError(_('Cannot create optimisation in the past.'))
        return value

    def _validate_options(self, ro_data, options):
        serializer = ExternalOptionsOptimisationSerializerV2(
            data=copy.deepcopy(options),
            context={**self.context, 'day': ro_data['day'], 'type': ro_data['type'], 'merchant': ro_data['merchant']},
        )

        try:
            serializer.is_valid(raise_exception=True)
        except serializers.ValidationError as e:
            e.detail = {'options': e.detail}
            raise

        return serializer.validated_data

    def create(self, validated_data):
        options = validated_data.pop('options', {})
        instance = super().create(validated_data)
        task, _ = OptimisationTask.objects.get_or_create(optimisation=instance)
        task.begin()
        task.save(update_fields=('status',))
        ctx = self.context
        ctx['merchant'] = instance.merchant
        instance.backend.on_create(options, serializer_context=ctx)
        return instance

    @staticmethod
    def run_optimisation(instance):
        if instance.state != RouteOptimisation.STATE.FAILED:
            from route_optimisation.celery_tasks.optimisation import run_optimisation
            run_optimisation(instance.delayed_task, instance)
        return instance


class ExternalMultiROSerializer(serializers.ListSerializer):
    child = ExternalRouteOptimisationSerializer()

    def separate_data_by_merchant(self, data) -> list:
        options = data.pop('options', {})
        serializer = ManyMerchantsSeparateOptionsSerializer(
            data=copy.deepcopy(options),
            context={**self.context, 'day': data['day'], 'type': data['type']},
        )
        serializer.is_valid(raise_exception=True)
        result = []
        for merchant, options in serializer.data.items():
            data_copy = copy.deepcopy(data)
            data_copy['options'] = options
            data_copy['merchant'] = merchant
            result.append(data_copy)
        return result

    def to_internal_value(self, data):
        separated_data_by_merchant = None
        try:
            separated_data_by_merchant = self.separate_data_by_merchant(data)
            result = super().to_internal_value(separated_data_by_merchant)
            return result
        except serializers.ValidationError as e:
            if not separated_data_by_merchant:
                e.detail = {'options': e.detail}
            elif isinstance(e.detail, list):
                e.detail = e.detail[0]
            raise

    def create(self, validated_data):
        data_for_create = tuple(map(self.child.convert_external_data, validated_data))
        created_instances = tuple(map(self.child.create, data_for_create))
        optimisations = tuple(map(self.child.run_optimisation, created_instances))
        return optimisations
