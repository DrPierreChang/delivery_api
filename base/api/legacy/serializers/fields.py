from __future__ import unicode_literals

from django.db.models import Q

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.fields import CharField

from base.models import Member


class PasswordField(CharField):
    def __init__(self, **kwargs):
        style = {
            'input_type': 'password',
        }
        style.update(kwargs.get('style', {}))
        kwargs['style'] = style
        super(PasswordField, self).__init__(**kwargs)


class MarkdownField(serializers.CharField):
    def to_internal_value(self, data):
        # if data and not lxml.html.fromstring(data).find('.//*') is None:
        #     data = convert_html_to_markdown(data)
        return data


class MemberIDDriverField(serializers.Field):
    def to_internal_value(self, data):
        if not data:
            return None
        else:
            try:
                # Raised error, when we have user with member_id and other user with same id
                return Member.drivers.get(Q(member_id=data) | Q(id=data))
            except (ValueError, Member.DoesNotExist):
                raise ValidationError('You don\'t have a driver with this ID ({}).'.format(data))

    def to_representation(self, value):
        return value.member_id
