from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from ..v1.serializers import ResultAnswerSerializer, ResultChecklistSerializer


class V2ResultAnswerSerializer(ResultAnswerSerializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)

        if attrs['answer'].photos_required and len(attrs['photos']) == 0:
            raise serializers.ValidationError(
                {'answer_photos': _('Photos are required for this answer.')}, code='required',
            )

        return attrs


class V2ResultChecklistSerializer(ResultChecklistSerializer):
    answers = V2ResultAnswerSerializer(many=True, source='result_answers')
