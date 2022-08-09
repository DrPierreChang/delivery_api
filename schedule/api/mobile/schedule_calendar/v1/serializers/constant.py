from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers


class DailyConstScheduleSerializer(serializers.Serializer):
    start = serializers.TimeField(required=True, format='%H:%M')
    end = serializers.TimeField(required=True, format='%H:%M')
    day_off = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if ('start' in attrs) != ('end' in attrs):
            raise serializers.ValidationError(_('You must enter both time period values'), code='both_required')

        if ('start' in attrs) and ('end' in attrs) and (attrs['start'] >= attrs['end']):
            raise serializers.ValidationError(
                _('The start time should be less than the end time.'), code='invalid_range',
            )

        return super().validate(attrs=attrs)

    def bind(self, field_name, parent):
        # Needed to allow the use of numbers in source
        self.field_name = field_name
        self.parent = parent
        self.label = field_name.capitalize()
        self.source_attrs = [self.source]


class ConstScheduleSerializer(serializers.Serializer):
    mon = DailyConstScheduleSerializer(source=0, required=False)
    tue = DailyConstScheduleSerializer(source=1, required=False)
    wed = DailyConstScheduleSerializer(source=2, required=False)
    thu = DailyConstScheduleSerializer(source=3, required=False)
    fri = DailyConstScheduleSerializer(source=4, required=False)
    sat = DailyConstScheduleSerializer(source=5, required=False)
    sun = DailyConstScheduleSerializer(source=6, required=False)

    def update(self, instance, validated_data):
        for week_day, daily_schedule in validated_data.items():
            instance[week_day].update(daily_schedule)
        return instance
