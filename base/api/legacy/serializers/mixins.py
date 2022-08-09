from __future__ import unicode_literals

from django.contrib.auth import password_validation as validators
from django.contrib.auth.hashers import make_password

from rest_framework import serializers

from base.models import Car
from radaro_utils.serializers.mixins import BaseUnpackMixin

from ..serializers.fields import PasswordField


class SetPasswordMixin(serializers.Serializer):
    password = PasswordField(required=True, write_only=True)
    old_password = PasswordField(required=False, write_only=True)

    def validate_password(self, value):
        if getattr(self.instance, 'password', None):
            old_pass = self.initial_data.get('old_password', None)
            if not old_pass:
                raise serializers.ValidationError('You should provide your old password.')
            else:
                if not self.instance.check_password(old_pass):
                    raise serializers.ValidationError('Old password is not valid.')
                else:
                    if value == old_pass:
                        raise serializers.ValidationError('New password and old password are equal.')
        validators.validate_password(value, self.instance)
        return make_password(value)


class CarUnpackMixin(BaseUnpackMixin):
    def unpack_fields(self, validated_data):
        super(CarUnpackMixin, self).unpack_fields(validated_data)
        for name in self.car_field_names:
            try:
                data = validated_data.pop(name)
                user = self.context['request'].user
                user.car = Car.objects.update_or_create(defaults=data, member__id=user.id)[0]
            except KeyError:
                pass
