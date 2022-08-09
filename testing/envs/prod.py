import copy

from .staging import SETTINGS as STAGING

BASE_URL = 'api.radaro.com'

SETTINGS = copy.deepcopy(STAGING)
SETTINGS['manager']['default_driver'] = 44
SETTINGS.update({
    'url': BASE_URL,
    'driver': {
        'login': 'm-den-i@mail.ru',
        'password': 'dirtylittlesecret'
    }
})
