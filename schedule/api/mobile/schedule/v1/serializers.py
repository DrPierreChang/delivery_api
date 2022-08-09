from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from schedule.models import Schedule


class BreakSerializer(serializers.Serializer):
    start = serializers.TimeField(required=True, format='%H:%M')
    end = serializers.TimeField(required=True, format='%H:%M')

    def validate(self, attrs):
        if attrs['start'] >= attrs['end']:
            raise serializers.ValidationError(
                _('The start of the break must be before the end.'), code='invalid_break_range',
            )
        return attrs


class DailyScheduleSerializer(serializers.Serializer):
    start = serializers.TimeField(required=False, format='%H:%M')
    end = serializers.TimeField(required=False, format='%H:%M')
    day_off = serializers.BooleanField(default=False)
    one_time = serializers.BooleanField(default=False)
    breaks = BreakSerializer(required=False, many=True)

    def validate_breaks(self, attr):
        attr.sort(key=lambda b: b['start'])
        for index in range(len(attr) - 1):
            if attr[index]['end'] >= attr[index + 1]['start']:
                raise serializers.ValidationError(_('Break ranges overlap.'), code='overlap_breaks')
        return attr

    def validate(self, attrs):
        if ('start' in attrs) != ('end' in attrs):
            raise serializers.ValidationError(_('You must enter both time period values'), code='both_required')

        if not attrs.get('one_time', False) and attrs.get('breaks', []):
            raise serializers.ValidationError(_('Breaks are only available on one time schedule'))

        if attrs.get('day_off', False) and attrs.get('breaks', []):
            raise serializers.ValidationError(_("You can't add a weekend break."), code='day_off_break')

        if ('start' in attrs) and ('end' in attrs) and (attrs['start'] >= attrs['end']):
            raise serializers.ValidationError(
                _('The start time should be less than the end time.'), code='invalid_range',
            )

        return super().validate(attrs=attrs)


class WeekScheduleSerializer(serializers.Serializer):
    mon = DailyScheduleSerializer(source='0', required=False)
    tue = DailyScheduleSerializer(source='1', required=False)
    wed = DailyScheduleSerializer(source='2', required=False)
    thu = DailyScheduleSerializer(source='3', required=False)
    fri = DailyScheduleSerializer(source='4', required=False)
    sat = DailyScheduleSerializer(source='5', required=False)
    sun = DailyScheduleSerializer(source='6', required=False)

    weeks_list = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

    def validate(self, attrs):
        instance = self.root.instance
        instance.update_schedule(attrs)
        for weekday, daily_schedule in instance.week_schedule().items():
            weekday_name = self.weeks_list[weekday]
            if daily_schedule.get('breaks', []):
                if daily_schedule['start'] >= daily_schedule['breaks'][0]['start']:
                    raise serializers.ValidationError(
                        {weekday_name: _('The break went beyond working hours.')}, code='break_outside_schedule',
                    )
                if daily_schedule['breaks'][-1]['end'] >= daily_schedule['end']:
                    raise serializers.ValidationError(
                        {weekday_name: _('The break went beyond working hours.')}, code='break_outside_schedule',
                    )

        return instance.schedule

    def to_representation(self, instance):
        return super().to_representation(instance={str(date): s for date, s in instance.week_schedule().items()})

    def to_internal_value(self, data):
        data = super().to_internal_value(data)
        instance = self.root.instance
        schedule = {'constant': {}, 'one_time': {}}
        for day, daily_schedule in data.items():
            day = int(day)
            if daily_schedule.pop('one_time', False):
                schedule['one_time'][instance.convert_weekday_to_date(day)] = daily_schedule
            else:
                schedule['constant'][day] = daily_schedule

        return schedule


class MobileScheduleSerializer(serializers.ModelSerializer):
    member_id = serializers.PrimaryKeyRelatedField(read_only=True)
    week_schedule = WeekScheduleSerializer(required=True, source='*')

    class Meta:
        model = Schedule
        fields = ('member_id', 'week_schedule')

    def update(self, instance, validated_data):
        if validated_data:
            instance.schedule = validated_data
        return instance
