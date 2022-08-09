from django.dispatch import receiver

from reporting.models import Event
from reporting.signals import trigger_object_post_processing
from tasks.models import ConcatenatedOrder, Order


@receiver(trigger_object_post_processing)
def check_time_inside_geofence(event, **kwargs):
    if not type(event.object) in (Order, ConcatenatedOrder):
        return
    order = event.object

    if event.field == 'pickup_geofence_entered' and str(event.new_value) == 'False':
        time_inside_pickup_geofence = Event.objects.time_inside_pickup_geofence(order)
        order.set_duration_in_geofence_area('time_inside_pickup_geofence', time_inside_pickup_geofence)

    elif event.field == 'geofence_entered' and str(event.new_value) == 'False':
        time_inside_geofence = Event.objects.time_inside_geofence(order)
        order.set_duration_in_geofence_area('time_inside_geofence', time_inside_geofence)

    elif event.field == 'status':
        is_picked_up_status = (event.new_value == Order.PICKED_UP)
        picked_up_status_skipped = (event.new_value == Order.IN_PROGRESS and event.object.time_at_pickup is None)
        if is_picked_up_status or picked_up_status_skipped:
            time_at_pickup = Event.objects.time_at_pickup(order, event.new_value)
            order.set_duration_in_geofence_area('time_at_pickup', time_at_pickup)
        elif event.new_value == Order.DELIVERED:
            time_at_job = Event.objects.time_at_job(order)
            order.set_duration_in_geofence_area('time_at_job', time_at_job)


__all__ = ['check_time_inside_geofence', ]
