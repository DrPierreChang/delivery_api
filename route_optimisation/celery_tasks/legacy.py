from delivery.celery import app
from merchant.models import Merchant
from route_optimisation.models import RouteOptimisation
from route_optimisation.models.location import DriverRouteLocation
from routing.google import GoogleClient, merchant_registry


@app.task()
def legacy_async_driver_push(optimisation_id):
    optimisation = RouteOptimisation.objects.get(id=optimisation_id)
    optimisation.backend.result_keeper_class(optimisation).push_to_drivers(False)


@app.task()
def reverse_address_for_driver_route_location(driver_route_location_id, merchant_id):
    loc = DriverRouteLocation.objects.get(id=driver_route_location_id)
    if loc.address:
        return

    current_merchant = merchant_registry.get_merchant()
    if merchant_id and not current_merchant:
        merchant = Merchant.objects.get(id=merchant_id)
        with GoogleClient.track_merchant(merchant):
            loc.address = GoogleClient(timeout=5).reverse_geocode(
                loc.location, track_merchant=True, language=merchant.language
            )
    else:
        loc.address = GoogleClient(timeout=5).reverse_geocode(
            loc.location, track_merchant=True, language=current_merchant.language if current_merchant else None
        )
    loc.save(update_fields=['address'])
