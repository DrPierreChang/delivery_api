from django.conf import settings as django_settings

DEFAULT_SETTINGS = {
    'PHONE_SERIALIZER_FIELD': 'radaro_utils.radaro_phone.serializers.PhoneField'
}


class Settings(object):
    def __init__(self, settings, default_settings):
        self.settings = settings
        self.default_settings = default_settings

    def __getattr__(self, item):
        if item not in self.default_settings:
            raise AttributeError("Invalid settings: '%s'" % item)

        return getattr(self.settings, item, self.default_settings[item])


settings = Settings(django_settings, DEFAULT_SETTINGS)
