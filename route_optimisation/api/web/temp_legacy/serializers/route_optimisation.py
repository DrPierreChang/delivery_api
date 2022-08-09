from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from route_optimisation.api.fields import CurrentMerchantDefault
from route_optimisation.api.web.temp_legacy.serializers.driver_route import DriverRouteSerializer
from route_optimisation.api.web.temp_legacy.serializers.fields import LogField
from route_optimisation.api.web.temp_legacy.serializers.prefetch_utils import prefetch_for_route_optimisation
from route_optimisation.models import OptimisationTask, RouteOptimisation


class RouteOptimisationListSerializer(serializers.ListSerializer):
    @property
    def data(self):
        prefetch_for_route_optimisation(self.instance)
        return super().data


class RouteOptimisationSerializer(serializers.ModelSerializer):
    merchant = serializers.HiddenField(default=CurrentMerchantDefault(), write_only=True)
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault(), write_only=True)
    options = serializers.DictField()
    routes = DriverRouteSerializer(many=True, read_only=True)
    task_status = serializers.SerializerMethodField()
    group = serializers.SerializerMethodField()
    log = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = RouteOptimisation
        fields = ('id', 'type', 'day', 'merchant', 'created_by', 'options',
                  'routes', 'state', 'task_status',
                  'group', 'customers_notified', 'log',)
        extra_kwargs = {
            'state': {'read_only': True},
            'customers_notified': {'read_only': True}
        }
        list_serializer_class = RouteOptimisationListSerializer

    @property
    def data(self):
        if self.instance is not None:
            prefetch_for_route_optimisation([self.instance])
        return super().data

    def create(self, validated_data):
        options = validated_data.pop('options', {})
        instance = super().create(validated_data)
        task, _ = OptimisationTask.objects.get_or_create(optimisation=instance)
        task.begin()
        task.save(update_fields=('status',))
        instance.backend.on_create(options, serializer_context=self.context)
        if instance.state != RouteOptimisation.STATE.FAILED:
            from route_optimisation.celery_tasks.optimisation import run_optimisation
            run_optimisation(task, instance)
        return instance

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
