from django.conf import settings

SPEED = 40 / 3.6
MAX_ACCURACY_RANGE = settings.MAX_ACCURACY_RANGE
ACCURACY = MAX_ACCURACY_RANGE / 3
BASE_DIR = settings.BASE_DIR
TESTING_DIR = BASE_DIR + '/testing'
TIMEOUT = 15
