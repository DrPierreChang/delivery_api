from django.conf import settings
from django.utils.encoding import smart_text

from routing.google import GoogleClient


class AddressGeocoder(object):
    def geocode(self, value, regions, language=None):
        for region in regions:
            loc_obj = GoogleClient().geocode(
                value, region, track_merchant=True, language=language or settings.LANGUAGE_CODE
            )
            if loc_obj:
                return dict(
                    location=u'{:.6f},{:.6f}'.format(*loc_obj[1]),
                    address=smart_text(loc_obj.address, encoding='utf-8', strings_only=False, errors='strict'),
                    raw_address=value,
                )
