from __future__ import absolute_import, unicode_literals

import re
from collections import namedtuple
from datetime import datetime
from math import ceil


def filter_dict(d, keys):
    return dict(filter(lambda i: i[0] in keys, d.items()))


def exclude_keys_from_dict(d, keys):
    return dict(filter(lambda k, v: k not in keys, d.items()))


def remove_non_hex(line):
    return re.sub(r'[^0-9a-fA-F]', '', line)


def get_sms_info(msg_text):
    IS_NOT_BASESTRING_MSG = 'Data for SMS is not text.'
    gsm0338_codes = [10, 13, 27, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53,
                     54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78,
                     79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 95, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106,
                     107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 161, 163, 164, 165,
                     167, 191, 196, 197, 198, 199, 201, 209, 214, 216, 220, 223, 224, 228, 229, 230, 232, 233, 236, 241,
                     242, 246, 248, 249, 252, 915, 916, 920, 923, 926, 928, 931, 934, 936, 937]

    extended_gsm0338_codes = [12, 91, 92, 93, 94, 123, 124, 125, 126, 164, 8364]

    MAX_MULTIPART_MSG_SEGMENT_SIZE_UCS2 = 67
    MAX_SINGLE_MSG_SEGMENT_SIZE_UCS2 = 70

    MAX_MULTIPART_MSG_SEGMENT_SIZE_7BIT = 153
    MAX_SINGLE_MSG_SEGMENT_SIZE_7BIT = 160

    def check_type(iso_txt):
        if not isinstance(iso_txt, str):
            raise ValueError(IS_NOT_BASESTRING_MSG)

    def is_iso_gsm_0338(cur_char):
        return cur_char in gsm0338_codes

    def is_extended(cur_char):
        return cur_char in extended_gsm0338_codes

    def is_encodable_gsm_0338(iso_string):
        return all([is_iso_gsm_0338(ch) or is_extended(ch) for ch in map(ord, iso_string)])

    def get_max_message_part_size(iso_text):
        message_size = {
            'single': 0,
            'multipart': 0
        }
        if is_encodable_gsm_0338(iso_text):
            message_size['single'] = MAX_SINGLE_MSG_SEGMENT_SIZE_7BIT
            message_size['multipart'] = MAX_MULTIPART_MSG_SEGMENT_SIZE_7BIT
        else:
            message_size['single'] = MAX_SINGLE_MSG_SEGMENT_SIZE_UCS2
            message_size['multipart'] = MAX_MULTIPART_MSG_SEGMENT_SIZE_UCS2
        return message_size

    check_type(msg_text)
    message_size = get_max_message_part_size(msg_text)

    def get_segment_count(iso_txt):
        return 1 if len(iso_txt) <= message_size['single'] else int(ceil(1. * len(iso_txt) / message_size['multipart']))

    def get_symbols_limit(iso_txt):
        return message_size['single'] if len(iso_txt) <= message_size['single'] else \
            int(ceil(1. * len(iso_txt) / message_size['multipart']) * message_size['multipart'])

    return {
        'segment_count': get_segment_count(msg_text),
        'symbols_limit': get_symbols_limit(msg_text)
    }


def format_upcoming_delivery_time(customer, dt):
    merchant = customer.merchant
    DT_TEMPLATE = '%H:%M'
    return dt.astimezone(merchant.timezone).strftime(DT_TEMPLATE)


DateTemplateFormat = namedtuple('DateTemplateFormat', ('US', 'DEFAULT'))
date_template_format = DateTemplateFormat('F j, Y, f a', 'j F Y, H:i')
