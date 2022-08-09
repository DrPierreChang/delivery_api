from __future__ import absolute_import

import re

from django.db.models import Q
from django.utils.encoding import smart_text

from radaro_utils.geo import AddressGeocoder
from routing.google import GoogleClient

from ..models import OrderLocation


class StringAddressToOrderLocation(object):
    def to_order_location(self, value: tuple, user):
        address, secondary_address = value
        secondary_address = secondary_address or ''
        processing_chain = [self.check_value_is_location, self.find_existing_order_location, self.geocode_value]
        for processing_func in processing_chain:
            loc_obj = processing_func(address, secondary_address, user)
            if loc_obj is not None:
                return loc_obj

    def check_value_is_location(self, address, secondary_address, *args):
        loc_obj = None
        if self.is_location_string(address):
            loc_obj, _ = OrderLocation.objects.get_or_create(
                location=address.replace(' ', ''),
                address=address,
                raw_address='',
                secondary_address=secondary_address,
            )
        return loc_obj

    def find_existing_order_location(self, address, secondary_address, *args):
        string_value = smart_text(address, encoding='utf-8', strings_only=False, errors='strict')
        return OrderLocation.objects.filter(
            (Q(address=string_value) | Q(raw_address=string_value)),
            secondary_address=secondary_address
        ).first()

    def geocode_value(self, address, secondary_address, user):
        regions = user.current_merchant.countries if hasattr(user, 'current_merchant') else ['AU', ]
        with GoogleClient.track_merchant(user.current_merchant):
            geocoded_data = AddressGeocoder().geocode(address, regions, user.current_merchant.language)
        if geocoded_data:
            geocoded_data.update({'secondary_address': secondary_address})
            return OrderLocation.objects.get_or_create(**geocoded_data)[0]

    def is_location_string(self, value):
        return re.match(r"^([-\d.]+),\s*([-\d.]+)$", value)
