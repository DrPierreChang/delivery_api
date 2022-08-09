import calendar
import logging
import random
import re
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

from rest_framework.pagination import PageNumberPagination

import html2text
from factory.fuzzy import FuzzyFloat

logger = logging.getLogger(__name__)


def password_is_valid(password, silent=False):
    if re.match(r'.*\d+.*', password) and re.match(r'.*[a-zA-z]+.*', password):
        return True
    else:
        if silent:
            return False
        else:
            raise ValidationError('Password should contain at least one latin letter and one digit.')


def day_in_future():
    return calendar.timegm((timezone.now().date() + timedelta(days=2)).timetuple())


class CustomPageNumberPagination(PageNumberPagination):
    page_size_query_param = 'page_size'
    max_page_size = 1000


def dictionaries_difference(dict1, dict2):
    keys = dict1.keys()
    diff_keys = []
    _dict_1 = {}
    _dict_2 = {}
    for key in keys:
        if dict1[key] != dict2[key]:
            diff_keys.append(key)
            _dict_1[key] = dict1[key]
            _dict_2[key] = dict2[key]

    return diff_keys, _dict_1, _dict_2


def generate_id(length, cmpr, prefix=None):
    pw_ten = 10 ** (length + 1)
    beg = 0
    end = pw_ten - 1
    if prefix:
        beg += prefix * pw_ten
        end += prefix * pw_ten
    _id = random.randint(beg, end)
    tries = 1
    while cmpr(_id):
        _id = random.randint(beg, end)
        tries += 1
    logger.info('Generated ID for {}. Collisions: {}'.format(cmpr.__name__, tries - 1))
    return _id


def random_with_n_digits(n):
    range_start = 10**(n-1)
    range_end = (10**n)-1
    return random.randint(range_start, range_end)


def convert_html_to_markdown(html):
    h2t = html2text.HTML2Text(bodywidth=0)
    return h2t.handle(html).replace('\n', '<br/>')


def get_fuzzy_location():
    return "%.6f,%.6f" % (FuzzyFloat(51, 57).fuzz(), FuzzyFloat(23, 33).fuzz())


def get_v2_fuzzy_location():
    return {'lat': FuzzyFloat(51, 57).fuzz(), 'lng': FuzzyFloat(23, 33).fuzz()}


class MobileAppVersionsConstants(object):
    ANDROID = 'android'
    IOS = 'ios'
    TA_ANDROID = 'ta_android'
    TA_IOS = 'ta_ios'

    WIDGET_LABEL_MAP = {
        ANDROID: 'Android',
        IOS: 'iOS',
        TA_ANDROID: 'Android Truck Assist',
        TA_IOS: 'iOS Truck Assist',
    }

    APP_TYPES = [ANDROID, IOS, TA_ANDROID, TA_IOS]
