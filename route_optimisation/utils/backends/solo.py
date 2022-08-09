import logging

from route_optimisation.const import OPTIMISATION_TYPES, REFRESH_SOLO
from route_optimisation.engine.const import Algorithms
from route_optimisation.logging import EventType
from route_optimisation.utils.backends.base import OptimisationBackend
from route_optimisation.utils.backends.registry import backend_registry
from route_optimisation.utils.deletion import DeleteService
from route_optimisation.utils.managing import (
    SequenceReorderService,
    SoloMoveOrderPrepareService,
    SoloMoveOrderSaveService,
)
from route_optimisation.utils.results import SoloResultKeeper
from route_optimisation.utils.results.solo import RefreshSoloResultKeeper
from route_optimisation.utils.validation.validators import RefreshDummySoloOptions, SoloOptions
from routing.context_managers import GoogleApiRequestsTracker

logger = logging.getLogger('optimisation')


@backend_registry.register(OPTIMISATION_TYPES.SOLO)
class SoloOptimisationBackend(OptimisationBackend):
    options_validator_class = SoloOptions
    algorithm_name = Algorithms.ONE_DRIVER
    result_keeper_class = SoloResultKeeper
    deletion_class = DeleteService
    sequence_reorder_service_class = SequenceReorderService
    move_orders_prepare_class = SoloMoveOrderPrepareService
    move_orders_save_class = SoloMoveOrderSaveService
    refresh_backend_name = REFRESH_SOLO

    def on_create(self, options=None, serializer_context=None):
        super().on_create()
        options = options or {}
        serializer_context = serializer_context or {}
        self.validate_options(options, serializer_context)


@backend_registry.register(REFRESH_SOLO)
class RefreshSoloOptimisationBackend(OptimisationBackend):
    options_validator_class = RefreshDummySoloOptions
    algorithm_name = Algorithms.ONE_DRIVER
    result_keeper_class = RefreshSoloResultKeeper

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
