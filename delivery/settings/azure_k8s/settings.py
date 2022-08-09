from . import env_vars
from . import server_vars

from delivery import settings
settings.env_vars = env_vars
settings.server_vars = server_vars

from delivery.settings.remote import *

DATABASES['default']['OPTIONS'] = {'sslmode': 'require'}
