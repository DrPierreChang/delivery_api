from django.db.models import Q

from rest_framework import serializers


class UniquePhoneNumberValidation(object):
    _unique_message = '{type} with this phone number already exists.'

    def __init__(self, queryset, **kwargs):
        self.queryset = queryset
        super(UniquePhoneNumberValidation, self).__init__(**kwargs)

    def __call__(self, value):
        query = Q(phone=value)
        if self.queryset.filter(query).exists():
            raise serializers.ValidationError(self.get_message())

    def set_context(self, serializer_field):
        instance = getattr(serializer_field.parent, 'instance', None)
        if instance:
            self.queryset = self.queryset.exclude(id=instance.id)

    def get_message(self):
        return self._unique_message.format(type=self.queryset.model._meta.verbose_name).capitalize()
