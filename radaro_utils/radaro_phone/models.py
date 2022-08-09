from django.db import models


class PhoneField(models.CharField):
    description = "Phone number in international format (up to %(max_length)s symbols)"

    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = kwargs.get('max_length', 128)
        super(PhoneField, self).__init__(*args, **kwargs)
