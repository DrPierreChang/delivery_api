import copy

from django.utils.translation import gettext_lazy as _

from rest_framework import serializers

from route_optimisation.api.web.serializers.manage_orders import DriverRouteValidator
from route_optimisation.const import OPTIMISATION_TYPES
from route_optimisation.logging import EventType, log_item_registry, move_dummy_optimisation_log
from route_optimisation.models import DriverRoute, RefreshDummyOptimisation, RouteOptimisation
from route_optimisation.utils.validation.serializers import JobsIdsField
from tasks.models import Order


class OptionsRefreshRouteSerializer(serializers.Serializer):
    jobs_ids = JobsIdsField(
        queryset=Order.aggregated_objects.all(), required=False, allow_null=True, many=True, raise_not_exist=False,
    )


class RefreshRouteSerializer(serializers.Serializer):
    route = serializers.PrimaryKeyRelatedField(
        queryset=DriverRoute.objects.all(), required=False, validators=(DriverRouteValidator(),), allow_null=True,
    )
    options = OptionsRefreshRouteSerializer(source='*')

    def save(self, **kwargs):
        optimisation = self.instance
        dummy_optimisation = RefreshDummyOptimisation(
            optimisation, optimisation.day, optimisation.merchant,
            self.context['request'].user, backend_name=optimisation.backend.refresh_backend_name
        )

        options = copy.deepcopy(optimisation.options)

        if self.validated_data.get('jobs_ids', None) is None:
            options.pop('jobs_ids', None)
        else:
            options['jobs_ids'] = [job.id for job in self.validated_data['jobs_ids']]

        if optimisation.type == OPTIMISATION_TYPES.ADVANCED:
            if self.validated_data.get('route', None) is None:
                raise serializers.ValidationError({'route': _('This field is required.')}, code='required')
            else:
                options['route'] = self.validated_data['route'].id

        dummy_optimisation.backend.on_create(options, serializer_context=self.context)

        try:
            if dummy_optimisation.state == RouteOptimisation.STATE.FAILED:
                self.handle_fail(dummy_optimisation, optimisation)
        finally:
            move_dummy_optimisation_log(dummy_optimisation, optimisation, dev=False)

        from route_optimisation.celery_tasks import run_optimisation_refresh
        run_optimisation_refresh.delay(
            optimisation.id,
            dummy_optimisation.optimisation_options,
            dummy_optimisation.created_by.id
        )

    def handle_fail(self, dummy_optimisation, optimisation):
        last_validation_log_item = None
        for log_item in dummy_optimisation.optimisation_log.log['full']:
            if log_item.get('event') == EventType.VALIDATION_ERROR:
                last_validation_log_item = log_item
        error_text = None
        if last_validation_log_item:
            log_class = log_item_registry.get(last_validation_log_item.get('event'))
            error_text = log_class and log_class.build_message_for_web(last_validation_log_item, optimisation, [])
        raise serializers.ValidationError(error_text or 'Can not refresh')
