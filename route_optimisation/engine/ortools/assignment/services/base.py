from ortools.constraint_solver import pywrapcp

from ...context import BaseAssignmentContext


class BaseImproveRouteService:
    def __init__(self, context: BaseAssignmentContext, routing_manager: pywrapcp.RoutingIndexManager):
        self.context = context
        self.routing_manager = routing_manager


class BaseImproveRouteProcess(BaseImproveRouteService):
    def process(self, *args, **kwargs):
        raise NotImplementedError()
