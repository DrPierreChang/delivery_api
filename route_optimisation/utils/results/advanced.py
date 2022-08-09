from route_optimisation.push_messages.composers import NewRoutePushMessage

from .base import ResultKeeper
from .solo import RefreshSoloResultKeeper


class AdvancedResultKeeper(ResultKeeper):
    def push_to_drivers(self, successful):
        if not successful:
            return
        for driver_route in self.optimisation.routes.all():
            driver_route.driver.send_versioned_push(NewRoutePushMessage(self.optimisation, driver_route))


class RefreshAdvancedResultKeeper(RefreshSoloResultKeeper):
    pass
