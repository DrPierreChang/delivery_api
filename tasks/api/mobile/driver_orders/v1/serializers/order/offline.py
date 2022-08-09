from rest_framework import serializers

from radaro_utils.serializers.fields import UTCTimestampField
from radaro_utils.serializers.validators import ValidateLaterDoesNotExist
from reporting.models import Event
from tasks.models import Order


class OfflineOrderMixinSerializer(serializers.ModelSerializer):
    offline_happened_at = UTCTimestampField(required=False)

    class Meta:
        model = Order
        fields = ['offline_happened_at']
        abstract = True

    def validate_offline_happened_at(self, offline_happened_at):
        if self.instance:
            events = self.instance.events.all().filter(event=Event.CHANGED)
            ValidateLaterDoesNotExist(events, 'happened_at')(offline_happened_at)
        return offline_happened_at

    def validate(self, attrs):
        if 'offline_happened_at' in attrs:
            attrs['changed_in_offline'] = True

        return super().validate(attrs)
