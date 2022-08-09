import copy

from rest_framework import serializers

from route_optimisation.logging import EventType, log_item_registry, move_dummy_optimisation_log
from route_optimisation.models import RefreshDummyOptimisation, RouteOptimisation


class RefreshRouteSerializer(serializers.Serializer):
    def save(self, **kwargs):
        optimisation = self.instance.optimisation
        dummy_optimisation = RefreshDummyOptimisation(
            optimisation, optimisation.day, optimisation.merchant,
            self.context['request'].user, backend_name=optimisation.backend.refresh_backend_name
        )

        options = copy.deepcopy(optimisation.options)
        options.pop('jobs_ids', None)
        options['route'] = self.instance.id

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
