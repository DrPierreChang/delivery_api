import json
import mimetypes

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.utils.encoding import force_text
from django.utils.formats import get_format
from django.utils.http import urlsafe_base64_decode

from rest_framework import status

import requests
import sentry_sdk

TINY_LINK_KEY = 'tiny-link-({})'


def shortcut_link_safe(original_link, many=False):
    try:
        return shortcut_link(original_link, many)

    except Exception as ex:
        sentry_sdk.capture_exception(ex)

        if many:
            return {
                link: cache.get(TINY_LINK_KEY.format(link), link)
                for link in original_link
            }
        else:
            return original_link


def shortcut_link(original_link, many=False):
    SERVICE_LINK = 'https://rtra.cc/developers/api/short-links/'
    headers = {'content-type': 'application/json', 'Authorization': 'Token %s' % settings.RADARO_SHORTENER_TOKEN}

    if many:
        result = {}
        unprocessed_original_links = []
        for link in original_link:
            tiny_link = cache.get(TINY_LINK_KEY.format(link), None)
            if tiny_link:
                result[link] = tiny_link
            else:
                unprocessed_original_links.append({'original_link': link})

        resp = requests.post(SERVICE_LINK, data=json.dumps(unprocessed_original_links), headers=headers, timeout=1000)
        if resp.status_code != status.HTTP_200_OK:
            raise ValueError(str(resp.json()))

        for item in resp.json():
            original_link, tiny_link = item['original_link'], item['tiny_link']
            result[original_link] = tiny_link
            cache.set(TINY_LINK_KEY.format(original_link), tiny_link, 60 * 60 * 24)
        return result

    else:
        tiny_link = cache.get(TINY_LINK_KEY.format(original_link), None)
        if tiny_link:
            return tiny_link

        resp = requests.get(SERVICE_LINK, params={'original_link': original_link}, headers=headers, timeout=30)
        if resp.status_code != status.HTTP_200_OK:
            raise ValueError(str(resp.json()))

        tiny_link = resp.json()['tiny_link']
        cache.set(TINY_LINK_KEY.format(original_link), tiny_link, 60 * 60 * 24)
        return tiny_link


def get_content_types_for(modelpath_list=[]):
    """
    :param modelpath_list: list of "app_label.model" for every model
    :return: queryset of ContentType objects for lines from modelpath_list
    """
    apps, models = zip(*[line.split('.') for line in modelpath_list])
    qs = ContentType.objects.filter(app_label__in=apps, model__in=models)
    return qs


def guess_mimetype(file_name):
    mime_type, _ = mimetypes.guess_type(file_name)
    return mime_type


def get_date_format():
    return get_format('DATE_INPUT_FORMATS')[0]


class Pluralizer(object):
    def __init__(self, value):
        self.value = value

    def __format__(self, formatter):
        formatter = formatter.replace("N", str(self.value))
        start, _, suffixes = formatter.partition("/")
        singular, _, plural = suffixes.rpartition("/")

        return "{}{}".format(start, singular if self.value == 1 else plural)


st = 'Can\'t delete the {0:a skill/s} because you have "{0:N}" active {0:a job/s} that {0:a ha/s/ve} {0:a th/is/ese} {0:a skill/s}.'


def base64_to_text(base64_str):
    if not base64_str:
        return None

    try:
        text = force_text(urlsafe_base64_decode(base64_str))
    except ValueError:
        return None

    return text
