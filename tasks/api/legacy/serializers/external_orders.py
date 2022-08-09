from __future__ import absolute_import, unicode_literals

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.fields import empty

from radaro_utils.serializers.validators import ExternalIDUniqueTogetherValidator
from tasks.models.external import ExternalJob


class ExternalJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExternalJob
        fields = ('external_id', 'source', 'source_id', 'source_type')
        validators = [
            ExternalIDUniqueTogetherValidator(
                queryset=ExternalJob.objects.all(),
                fields=('external_id', 'source_id', 'source_type'),
                message="Order with such api key and id already exists."
            )
        ]

    def __init__(self, validate_extra=True, *args, **kwargs):
        self._validate_extra = validate_extra
        super(ExternalJobSerializer, self).__init__(*args, **kwargs)

    def run_validation(self, data=empty):
        try:
            value = super(ExternalJobSerializer, self).run_validation(data)
        except ValidationError as ex:
            if isinstance(data, dict) and 'external_id' in data and isinstance(ex.detail, dict):
                ex.detail['passed_external_id'] = data['external_id']
            raise ex
        return value


class NonUniqueExternalIDException(Exception):
    def __init__(self, message):
        self.message = message
