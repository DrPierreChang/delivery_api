import logging

from django.db.models import F
from django.utils import timezone, translation
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _

from delivery.celery import app
from notification.mixins import MessageTemplateStatus
from notification.utils import format_upcoming_delivery_time
from route_optimisation.const import RoutePointKind
from route_optimisation.logging import EventType
from route_optimisation.models import RouteOptimisation, RoutePoint

logger = logging.getLogger('optimisation')


@app.task()
def notify_ro_customers(optimisation_id):
    optimisation = RouteOptimisation.objects.get(id=optimisation_id)
    points = RoutePoint.objects\
        .filter(route__optimisation=optimisation, point_content_type__model='order') \
        .filter(point_kind=RoutePointKind.DELIVERY) \
        .exclude(start_time_known_to_customer=F('start_time'))\
        .prefetch_related('point_object')

    today_in_merchant_tz = timezone.now().astimezone(optimisation.merchant.timezone).date()
    with translation.override(optimisation.merchant.language):
        if today_in_merchant_tz != optimisation.day:
            day_postfix = _(' on {optimisation_day}').format(optimisation_day=date_format(optimisation.day, 'E j'))
        else:
            day_postfix = ''

    for point in points:
        order = point.point_object
        arrival_interval = point.planned_order_arrival_interval
        time_interval = '{start} - {end}{day}'.format(
            start=format_upcoming_delivery_time(order.customer, arrival_interval[0]),
            end=format_upcoming_delivery_time(order.customer, arrival_interval[1]),
            day=day_postfix,
        )
        context = {
            'time_interval': time_interval,
            'merchant': order.sub_branding or order.merchant,
            'customer_address': order.deliver_address.address,
            'url': order.get_order_url(),
        }
        order.notify_customer(
            template_type=MessageTemplateStatus.RO_UPCOMING_DELIVERY,
            extra_context=context,
        )
        point.start_time_known_to_customer = point.start_time
        point.save(update_fields=('start_time_known_to_customer', ))
    logger.info(None, extra=dict(obj=optimisation, event=EventType.NOTIFY_CUSTOMERS,
                                 event_kwargs={'code': 'success'}))
