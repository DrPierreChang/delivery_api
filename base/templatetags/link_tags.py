from django import template

register = template.Library()

DEFAULT = 'default'
NTI = 'nti'

links = {
    'SMS': {
        DEFAULT: 'https://rtra.cc/s/radaro',
        NTI: 'https://rtra.cc/s/truckassist',
    },
    'ANDROID_APP': {
        DEFAULT: 'https://play.google.com/store/apps/details?id=com.radaro',
        NTI: 'https://play.google.com/store/apps/details?id=com.radaro.ta',
    },
    'IOS_APP': {
        DEFAULT: 'https://itunes.apple.com/us/app/radaro/id1131126957?ls=1&mt=8',
        NTI: 'https://itunes.apple.com/us/app/truck-assist/id1239705095?mt=8',
    },
    'SMS_DOWNLOAD_APP_TEXT': {
        DEFAULT: 'Download our driver app using the link below and join your team now!',
        NTI: 'Download our app using the link below to get started.'
    },
}


def get_merchant_type(merchant):
    return NTI if merchant.is_nti else DEFAULT


@register.simple_tag
def get_link(invite, link_type):
    return links[link_type][get_merchant_type(invite.merchant)]
