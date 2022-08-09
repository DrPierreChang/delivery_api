from rest_framework import serializers

from tasks.models import TerminateCode


class TerminateCodeSerializer(serializers.ModelSerializer):
    type = serializers.ChoiceField(choices=TerminateCode.TYPE_CHOICES)

    class Meta:
        model = TerminateCode
        fields = ('code', 'type', 'name', 'is_comment_necessary')
