from django.conf import settings as django_settings


class LazySettings(object):

    @property
    def PANDAS_CHUNKSIZE(self):
        return django_settings.RADARO_CSV.get('PANDAS_CHUNKSIZE', None)


settings = LazySettings()
