from datetime import timedelta

from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from radaro_utils.serializers.mobile.serializers import DynamicKeySerializer


class BreakSerializer(serializers.Serializer):
    start = serializers.TimeField(required=True, format='%H:%M')
    end = serializers.TimeField(required=True, format='%H:%M')

    def validate(self, attrs):
        if attrs['start'] >= attrs['end']:
            raise serializers.ValidationError(
                _('The start of the break must be before the end.'), code='invalid_break_range',
            )
        return attrs


class DailyOneTimeScheduleSerializer(serializers.Serializer):
    start = serializers.TimeField(required=False, format='%H:%M')
    end = serializers.TimeField(required=False, format='%H:%M')
    day_off = serializers.BooleanField(default=False)
    breaks = BreakSerializer(required=False, many=True)

    def validate_breaks(self, attr):
        attr.sort(key=lambda b: b['start'])
        for index in range(len(attr) - 1):
            if attr[index]['end'] >= attr[index + 1]['start']:
                raise serializers.ValidationError(_('Break ranges overlap.'), code='overlap_breaks')
        return attr

    def validate(self, attrs):
        if not attrs.get('breaks', []):
            attrs.pop('breaks', [])

        if ('start' in attrs) != ('end' in attrs):
            raise serializers.ValidationError(_('You must enter both time period values'), code='both_required')

        if ('start' in attrs) and ('end' in attrs) and (attrs['start'] >= attrs['end']):
            raise serializers.ValidationError(
                _('The start time should be less than the end time.'), code='invalid_range',
            )

        if 'breaks' in attrs and attrs.get('day_off', False):
            raise serializers.ValidationError(_("You can't add a weekend break."), code='day_off_break')

        return super().validate(attrs=attrs)


class OneTimeScheduleSerializer(DynamicKeySerializer):
    key_field = serializers.DateField()
    value_field = DailyOneTimeScheduleSerializer(required=False)

    def validate_key_field(self, day):
        today = self.root.instance.today

        if day < today:
            raise serializers.ValidationError('You cannot set a schedule for the past day ')
        if today + timedelta(days=7) < day:
            raise serializers.ValidationError('You cannot set a schedule later than a week ')
        return day

    def validate_value_field(self, value):
        if not value or value == {'day_off': False}:
            return None
        return value

    def update(self, instance, validated_data):
        instance = super().update(instance, validated_data)

        today = self.root.instance.today
        for day in list(instance.keys()):
            if day < today:
                del instance[day]
        return instance
