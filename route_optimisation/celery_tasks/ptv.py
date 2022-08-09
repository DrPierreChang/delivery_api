from operator import attrgetter

from delivery.celery import app
from route_optimisation.models import DriverRoute, RouteOptimisation
from routing.google import GoogleClient


@app.task()
def ptv_import_calculate_driving_distance(optimisation_id):
    optimisation = RouteOptimisation.objects.all().select_related('merchant').get(id=optimisation_id)
    with GoogleClient.track_merchant(optimisation.merchant):
        gc = GoogleClient()
        for route in DriverRoute.objects.filter(optimisation_id=optimisation_id):
            if route.driving_distance:
                continue
            locations = list(map(attrgetter('point_location.location'), route.points.prefetch_related('point_object')))
            route.driving_distance = sum(gc.directions_distance(locations[0], *locations[1:], track_merchant=True))
            route.save(update_fields=('driving_distance',))
