from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from schedule.models import Schedule

from .constant import ConstScheduleSerializer
from .one_time import OneTimeScheduleSerializer


class CalendarScheduleSerializer(serializers.Serializer):
    constant = ConstScheduleSerializer()
    one_time = OneTimeScheduleSerializer()

    def validate(self, attrs):
        instance = self.root.instance.schedule.copy()
        if 'constant' in attrs:
            instance['constant'] = self.fields['constant'].update(instance['constant'], attrs['constant'])
        if 'one_time' in attrs:
            instance['one_time'] = self.fields['one_time'].update(instance['one_time'], attrs['one_time'])

        for day, daily_schedule in instance['one_time'].items():
            final_schedule = {**instance['constant'][day.weekday()], **daily_schedule}
            if final_schedule.get('breaks', []):
                if final_schedule['start'] >= final_schedule['breaks'][0]['start']:
                    raise serializers.ValidationError(
                        {'one_time': {day.isoformat(): _('The break went beyond working hours.')}},
                        code='break_outside_schedule',
                    )
                if final_schedule['breaks'][-1]['end'] >= final_schedule['end']:
                    raise serializers.ValidationError(
                        {'one_time': {day.isoformat(): _('The break went beyond working hours.')}},
                        code='break_outside_schedule',
                    )

        return instance

    def update(self, instance, validated_data):
        return validated_data


class MobileCalendarScheduleSerializer(serializers.ModelSerializer):
    member_id = serializers.PrimaryKeyRelatedField(read_only=True)
    schedule = CalendarScheduleSerializer(required=True)

    class Meta:
        model = Schedule
        fields = ('member_id', 'schedule')

    def update(self, instance, validated_data):
        if 'schedule' in validated_data:
            instance.schedule = self.fields['schedule'].update(instance.schedule, validated_data['schedule'])
        instance.save()
        return instance
