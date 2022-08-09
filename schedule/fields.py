from datetime import date, time

from django.contrib.postgres.fields import JSONField
from django.utils import timezone

from rest_framework import serializers

from radaro_utils.serializers.mobile.serializers import DynamicKeySerializer


def default_daily_schedule_dict():
    return {
        'start': time(hour=9),
        'end': time(hour=17),
        'day_off': False,
    }


def default_constant_schedule_dict():
    week_schedule = {
        weekday: default_daily_schedule_dict()
        for weekday in range(0, 7)
    }
    return week_schedule


def default_schedule_dict():
    default_schedule = {
        'constant': default_constant_schedule_dict(),
        'one_time': {},
    }
    return default_schedule


class DBDailyConstantScheduleSerializer(serializers.Serializer):
    start = serializers.TimeField(default=time(hour=9), required=False)
    end = serializers.TimeField(default=time(hour=17), required=False)
    day_off = serializers.BooleanField(default=False)

    def bind(self, field_name, parent):
        field_name = field_name.lstrip('n_')
        return super().bind(field_name, parent)


class DBConstantScheduleSerializer(serializers.Serializer):
    # The "n_" prefix is needed to place the field in the serializer and is not used anywhere else
    n_0 = DBDailyConstantScheduleSerializer(default=default_daily_schedule_dict, required=False)
    n_1 = DBDailyConstantScheduleSerializer(default=default_daily_schedule_dict, required=False)
    n_2 = DBDailyConstantScheduleSerializer(default=default_daily_schedule_dict, required=False)
    n_3 = DBDailyConstantScheduleSerializer(default=default_daily_schedule_dict, required=False)
    n_4 = DBDailyConstantScheduleSerializer(default=default_daily_schedule_dict, required=False)
    n_5 = DBDailyConstantScheduleSerializer(default=default_daily_schedule_dict, required=False)
    n_6 = DBDailyConstantScheduleSerializer(default=default_daily_schedule_dict, required=False)

    def to_internal_value(self, data):
        data = super().to_internal_value(data)
        data = {int(key): value for key, value in data.items()}
        return data

    def to_representation(self, data):
        data = {str(key): value for key, value in data.items()}
        data = super().to_representation(data)
        return data


class NumberToDateField(serializers.IntegerField):
    def to_internal_value(self, data):
        number = super().to_internal_value(data)
        day = date.fromordinal(int(number))
        return day

    def to_representation(self, value):
        return str(value.toordinal())


class DBBreakSerializer(serializers.Serializer):
    start = serializers.TimeField(required=True)
    end = serializers.TimeField(required=True)


class DBDailyOneTimeScheduleSerializer(serializers.Serializer):
    start = serializers.TimeField(required=False)
    end = serializers.TimeField(required=False)
    day_off = serializers.BooleanField(default=False)
    breaks = DBBreakSerializer(required=False, many=True)


class DBOneTimeScheduleSerializer(DynamicKeySerializer):
    key_field = NumberToDateField()
    value_field = DBDailyOneTimeScheduleSerializer()

    def to_representation(self, value):
        minimal_day = timezone.now().date() - timezone.timedelta(days=1)
        value = {day: day_schedule for day, day_schedule in value.items() if day >= minimal_day}
        return super().to_representation(value)


class DBScheduleSerializer(serializers.Serializer):
    constant = DBConstantScheduleSerializer(default=default_constant_schedule_dict, required=False)
    one_time = DBOneTimeScheduleSerializer(default=dict, required=False)


class ScheduleField(JSONField):
    def __init__(self, *args, **kwargs):
        kwargs['default'] = default_schedule_dict
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        del kwargs['default']
        return name, path, args, kwargs

    def from_db_value(self, value, expression, connection):
        serializer = DBScheduleSerializer(data=value)
        try:
            serializer.is_valid(raise_exception=True)
            return serializer.validated_data
        except serializers.ValidationError:
            return default_schedule_dict()

    @staticmethod
    def _prepare_for_saving(value):
        if value.get('prepared_for_saving', False):
            return value

        serializer = DBScheduleSerializer(value)
        schedule = serializer.data

        schedule['prepared_for_saving'] = True
        return schedule

    def to_python(self, value):
        return self._prepare_for_saving(value)

    def get_prep_value(self, value):
        schedule = self._prepare_for_saving(value)
        del schedule['prepared_for_saving']
        return super().get_prep_value(schedule)
