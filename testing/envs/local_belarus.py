import copy

from .staging import SETTINGS as STAGING

SETTINGS = copy.deepcopy(STAGING)
SETTINGS.update({
    'url': 'http://localhost:8000',
    'driver': {
        'login': 'm-den-i@yandex.by',
        'password': 'dirtylittlesecret'
    },
    'manager': {
        'login': 'denis@razortheory.com',
        'password': 'kurlykkurlyk',
        'default_driver': 22,
        'default_job': SETTINGS['manager']['default_job']
    }
})
