from rest_framework import serializers

from tasks.models import Order, TerminateCode


class TerminateCodeNumberSerializer(serializers.ModelSerializer):
    class Meta:
        model = TerminateCode
        fields = ('code', 'name', 'type', 'is_comment_necessary')


class TerminateCodesSerializer(serializers.ModelSerializer):
    codes = TerminateCodeNumberSerializer(many=True, source='terminate_codes', required=False, read_only=True)

    class Meta:
        model = Order
        fields = ('codes', 'comment')
        extra_kwargs = {
            'comment': {'source': 'terminate_comment'},
        }
