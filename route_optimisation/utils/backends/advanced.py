import logging

from route_optimisation.const import OPTIMISATION_TYPES, REFRESH_ADVANCED
from route_optimisation.engine.const import Algorithms
from route_optimisation.logging import EventType
from route_optimisation.utils.deletion import DeleteService
from route_optimisation.utils.managing import (
    AdvancedMoveOrderPrepareService,
    AdvancedMoveOrderSaveService,
    SequenceReorderService,
)
from route_optimisation.utils.results import AdvancedResultKeeper
from route_optimisation.utils.validation.validators import AdvancedOptions, RefreshDummyAdvancedOptions
from routing.context_managers import GoogleApiRequestsTracker

from ..results.advanced import RefreshAdvancedResultKeeper
from .base import OptimisationBackend
from .registry import backend_registry

logger = logging.getLogger('optimisation')


@backend_registry.register(OPTIMISATION_TYPES.ADVANCED)
class AdvancedOptimisationBackend(OptimisationBackend):
    options_validator_class = AdvancedOptions
    algorithm_name = Algorithms.GROUP
    result_keeper_class = AdvancedResultKeeper
    deletion_class = DeleteService
    sequence_reorder_service_class = SequenceReorderService
    move_orders_prepare_class = AdvancedMoveOrderPrepareService
    move_orders_save_class = AdvancedMoveOrderSaveService
    refresh_backend_name = REFRESH_ADVANCED

    def on_create(self, options=None, serializer_context=None):
        super().on_create()
        options = options or {}
        serializer_context = serializer_context or {}
        self.validate_options(options, serializer_context)


@backend_registry.register(REFRESH_ADVANCED)
class RefreshAdvancedOptimisationBackend(OptimisationBackend):
    options_validator_class = RefreshDummyAdvancedOptions
    algorithm_name = Algorithms.ONE_DRIVER
    result_keeper_class = RefreshAdvancedResultKeeper

    def on_create(self, options=None, serializer_context=None):
        super().on_create()
        options = options or {}
        serializer_context = serializer_context or {}
        self.validate_options(options, serializer_context)

    def on_finish(self, engine_result, **params):
        super().on_finish(engine_result, **params)
        logger.info(None, extra=dict(obj=self.optimisation, event=EventType.REFRESH_OPTIONS,
                                     event_kwargs={'optimisation_options': self.optimisation.optimisation_options}))

    def track_api_requests_stat(self, tracker: GoogleApiRequestsTracker):
        raise NotImplementedError()
