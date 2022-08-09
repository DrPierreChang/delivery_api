from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from route_optimisation.api.fields import CurrentMerchantDefault
from route_optimisation.api.web.serializers.fields import LogField
from route_optimisation.const import OPTIMISATION_TYPES
from route_optimisation.models import OptimisationTask, RouteOptimisation


class SoloOptimisationDayDefault:
    def __init__(self):
        self.merchant = None

    def set_context(self, serializer_field):
        self.merchant = serializer_field.context['request'].user.current_merchant

    def __call__(self):
        return timezone.now().astimezone(self.merchant.timezone).date()

    def __repr__(self):
        return self.__class__.__name__


class CreateRouteOptimisationSerializer(serializers.ModelSerializer):
    merchant = serializers.HiddenField(default=CurrentMerchantDefault())
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())
    type = serializers.HiddenField(default=OPTIMISATION_TYPES.SOLO)
    day = serializers.DateField(default=SoloOptimisationDayDefault(), required=False, allow_null=False)
    options = serializers.DictField(write_only=True)
    task_status = serializers.SerializerMethodField()
    log = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = RouteOptimisation
        fields = ('id', 'type', 'day', 'merchant', 'created_by', 'options',
                  'state', 'task_status', 'log',)

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

    def validate_day(self, value):
        if value < timezone.now().astimezone(self.context['request'].user.current_merchant.timezone).date():
            raise serializers.ValidationError(_('Cannot create optimisation in the past.'))
        return value

    def get_task_status(self, optimisation):
        if hasattr(optimisation, 'delayed_task'):
            return optimisation.delayed_task.status

    def get_log(self, optimisation):
        return LogField().to_representation(optimisation.optimisation_log, optimisation=optimisation)


class OptimisationTaskSerializer(serializers.ModelSerializer):

    class Meta:
        model = OptimisationTask
        fields = serializers.ALL_FIELDS
