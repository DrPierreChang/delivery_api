import json
import logging

from django.conf import settings

from geopy import GoogleV3

from routing.google import merchant_registry

logger = logging.getLogger(__name__)


def get_data_for_external_job(order):
    gc_engine = GoogleV3(api_key=settings.GOOGLE_API_KEY, channel=merchant_registry.get_google_api_channel())
    country_identifier = order.customer.zipcode or order.customer.state
    location_raw = "{}, {}, {}".format(country_identifier, order.customer.city, order.customer.address)
    loc_search_obj = gc_engine.geocode(location_raw)

    if not loc_search_obj:
        logger.info("Invalid location row: {0} for order with id {1}".format(location_raw, order.id))

    location = "{},{}".format(loc_search_obj[1][0], loc_search_obj[1][1])

    data = dict()

    extra_data = dict(
        title=order.get_title(),
        customer=get_data_for_customer(order.customer),
        deliver_address=dict(location=location,
                             address=location_raw),
        comment=order.get_comment(),
        )

    if order.get_deliver_before():
        data['deliver_before'] = order.get_deliver_before()

    data['external_id'] = order.id
    data['extra'] = json.dumps(extra_data)

    return data


def get_data_for_customer(customer):
    result = dict()
    result['name'] = customer.get_name()
    result['phone'] = customer.get_phone()
    result['email'] = customer.get_email()

    return result
