# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.apps import AppConfig

from radaro_utils.radaro_phone.settings import settings as phone_settings


class RadaroPhoneConfig(AppConfig):
    name = 'radaro_utils.radaro_phone'

    def ready(self):
        """
        Update DRF for using custom serializer for PhoneField like for other db fields. 
        """
        from importlib import import_module

        from rest_framework.serializers import ModelSerializer

        from . import models

        _module, _serializer_name = phone_settings.PHONE_SERIALIZER_FIELD.rsplit('.', 1)
        serializer_module = import_module(_module)
        serializer_field = getattr(serializer_module, _serializer_name)

        field_mapping = ModelSerializer.serializer_field_mapping

        field_mapping.update({
            models.PhoneField: serializer_field,
        })
