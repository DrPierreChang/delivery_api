import copy

from .staging import SETTINGS as STAGING

SETTINGS = copy.deepcopy(STAGING)
SETTINGS.update({
    'url': 'http://localhost:8000',
    'driver': {
        'login': 'm-den-i@mail.ru',
        'password': 'dirtylittlesecret'
    },
    'manager': {
        'login': 'test1@manager.com',
        'password': 'crackme5times',
        'default_driver': 26,
        'default_job': SETTINGS['manager']['default_job']
    }
})
