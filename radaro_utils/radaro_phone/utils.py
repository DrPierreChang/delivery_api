import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from constance import config
from phonenumbers import (
    NumberParseException,
    PhoneMetadata,
    PhoneNumberFormat,
    format_number,
    is_valid_number,
    parse,
    region_code_for_number,
)


def make_phone_or_error(phone, regions, error_raising):
    def raise_validation_error(msg):
        if force_error_raising or error_raising:
            raise ValidationError(default_error_msg or msg)

    def to_e164_with_validation(phone, region):
        try:
            numobj = parse(phone, region)
        except NumberParseException as exc:
            raise_validation_error(str(exc))
        else:
            if region_code_for_number(numobj) not in regions:
                raise_validation_error(_('Not supported region for merchant.'))
            elif not is_valid_number(numobj):
                error_msg = ngettext("Invalid phone number for merchant's region.",
                                     "Invalid phone number for merchant's regions.",
                                     int(bool(region)))
                raise_validation_error(error_msg)
            else:
                return format_number(numobj, PhoneNumberFormat.E164)

    if not phone:
        return
    if not regions:
        regions = config.ALLOWED_COUNTRIES
    with_leading_plus = phone.startswith('+')
    force_error_raising = False
    default_error_msg = None

    if with_leading_plus:
        return to_e164_with_validation(phone, None)
    else:
        if len(regions) != 1:
            default_error_msg = _('Phone must be in international format since '
                                  'the merchant operates in multiple countries.')
            return to_e164_with_validation('+%s' % phone, None)
        else:
            try:
                force_error_raising = True
                return to_e164_with_validation('+%s' % phone, None)
            except ValidationError:
                force_error_raising = False
                return to_e164_with_validation('%s' % phone, regions[0])


def e164_phone_format(phone, regions):
    formatted_phone = make_phone_or_error(phone, regions, error_raising=False)
    return formatted_phone or re.sub(r'[\s-]', '', phone)


def phone_is_valid(phone, regions):
    return bool(make_phone_or_error(phone, regions, error_raising=True))


def phone_to_international_format(phone, regions=None):
    regions = regions or []
    region = regions[0] if len(regions) == 1 else None
    num_obj = parse(phone, region)
    return format_number(num_obj, PhoneNumberFormat.INTERNATIONAL)


def phone_is_mobile(phone):
    num_obj = parse(phone)
    meta = PhoneMetadata.metadata_for_region(region_code_for_number(num_obj))
    return bool(re.match(meta.mobile.national_number_pattern, str(num_obj.national_number)))
