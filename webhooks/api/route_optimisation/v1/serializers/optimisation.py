import copy

from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from route_optimisation.api.fields import CurrentMerchantDefault
from route_optimisation.models import OptimisationTask, RouteOptimisation

from .driver_route import ExternalDriverRouteSerializer
from .fields import LogField
from .options import ExternalOptionsOptimisationSerializer


class ExternalRouteOptimisationSerializerBase(serializers.ModelSerializer):
    merchant = serializers.HiddenField(default=CurrentMerchantDefault(), write_only=True)
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault(), write_only=True)
    options = serializers.DictField()
    task_status = serializers.SerializerMethodField()
    group = serializers.SerializerMethodField()
    log = serializers.SerializerMethodField(read_only=True)
    routes = ExternalDriverRouteSerializer(many=True, read_only=True)

    class Meta:
        model = RouteOptimisation
        fields = ('id', 'type', 'day', 'merchant', 'created_by', 'options',
                  'routes', 'state', 'task_status',
                  'group', 'customers_notified', 'log',)
        extra_kwargs = {
            'state': {'read_only': True},
            'customers_notified': {'read_only': True}
        }

    def _validate_options(self, ro_data, options):
        raise NotImplementedError()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['options'].pop('jobs_ids', None)
        data['options'].pop('drivers_ids', None)
        return data

    def convert_external_data(self, data):
        options = data.get('options', {})
        validated_options = self._validate_options(data, options)

        options.pop('jobs_ids', None)
        jobs_ids = set()
        if validated_options.get('order_ids', None):
            jobs_ids |= {order.id for order in validated_options['order_ids']}
        if validated_options.get('external_ids', None):
            jobs_ids |= {order.id for order in validated_options['external_ids']}
        if jobs_ids:
            options['jobs_ids'] = list(jobs_ids)

        options['drivers_ids'] = [driver.id for driver in validated_options['member_ids']]

        data['options'] = options
        return data

    def get_task_status(self, optimisation):
        if hasattr(optimisation, 'delayed_task'):
            return optimisation.delayed_task.status

    def validate_day(self, value):
        if value < timezone.now().astimezone(self.context['request'].user.current_merchant.timezone).date():
            raise serializers.ValidationError(_('Cannot create optimisation in the past.'))
        return value

    def get_group(self, optimisation):
        return optimisation.group

    def get_log(self, optimisation):
        return LogField().to_representation(optimisation.optimisation_log, optimisation=optimisation)


class ExternalRouteOptimisationSerializer(ExternalRouteOptimisationSerializerBase):
    def create(self, validated_data):
        data = self.convert_external_data(validated_data)
        options = data.pop('options', {})
        instance = super().create(data)
        task, _ = OptimisationTask.objects.get_or_create(optimisation=instance)
        task.begin()
        task.save(update_fields=('status',))
        instance.backend.on_create(options, serializer_context=self.context)
        if instance.state != RouteOptimisation.STATE.FAILED:
            from route_optimisation.celery_tasks.optimisation import run_optimisation
            run_optimisation(task, instance)
        return instance

    def _validate_options(self, ro_data, options):
        serializer = ExternalOptionsOptimisationSerializer(
            data=copy.deepcopy(options),
            context={**self.context, 'day': ro_data['day'], 'type': ro_data['type'], 'merchant': ro_data['merchant']},
        )

        try:
            serializer.is_valid(raise_exception=True)
        except serializers.ValidationError as e:
            e.detail = {'options': e.detail}
            raise

        return serializer.validated_data


class ExternalRouteOptimisationEventsSerializer(serializers.Serializer):
    updated_at = serializers.DateTimeField()
    optimisation_info = ExternalRouteOptimisationSerializer()
    token = serializers.CharField(max_length=255)
    topic = serializers.CharField(max_length=128)
