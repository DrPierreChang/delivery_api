from django.core.validators import MinValueValidator
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers

from radaro_utils.radaro_csv.backends import PandasCSVBackend
from radaro_utils.radaro_csv.parsing.base import CSVModelMappingReader
from radaro_utils.radaro_csv.rest_framework.field_validators import HeaderControl
from radaro_utils.radaro_csv.rest_framework.mappers import PandasReadMapper

time_error_messages = {
    'invalid': _('Time has wrong format. Use hh:mm time format instead.'),
}


class CSVReadDriverSerializer(serializers.Serializer):
    driver_id = serializers.CharField(required=True, error_messages={'required': _('"driver_id" field is required.')})
    capacity = serializers.CharField(required=False)
    shift_start = serializers.CharField(required=False)
    shift_end = serializers.CharField(required=False)
    day_off = serializers.CharField(required=False)
    break_start_1 = serializers.CharField(required=False)
    break_end_1 = serializers.CharField(required=False)
    break_start_2 = serializers.CharField(required=False)
    break_end_2 = serializers.CharField(required=False)


class CSVValidateDriverSerializer(serializers.Serializer):
    line = serializers.IntegerField()
    driver_id = serializers.IntegerField(
        source='driver',
        error_messages={'required': _('"driver_id" field is required.')},
    )
    capacity = serializers.FloatField(required=False, validators=[MinValueValidator(limit_value=0)])
    shift_start = serializers.TimeField(source='schedule.start', error_messages=time_error_messages, required=False)
    shift_end = serializers.TimeField(source='schedule.end', error_messages=time_error_messages, required=False)
    day_off = serializers.BooleanField(source='schedule.day_off', required=False)
    break_start_1 = serializers.TimeField(
        source='schedule.breaks.1.start', error_messages=time_error_messages, required=False,
    )
    break_end_1 = serializers.TimeField(
        source='schedule.breaks.1.end', error_messages=time_error_messages, required=False,
    )
    break_start_2 = serializers.TimeField(
        source='schedule.breaks.2.start', error_messages=time_error_messages, required=False,
    )
    break_end_2 = serializers.TimeField(
        source='schedule.breaks.2.end', error_messages=time_error_messages, required=False,
    )

    def __init__(self, instance=None, *args, **kwargs):
        super().__init__(instance, *args, **kwargs)
        merchant = kwargs['context']['bulk'].merchant
        if merchant is None:
            return

        if not merchant.enable_job_capacity:
            del self.fields['capacity']

    def validate_driver_id(self, value):
        from base.models import Member
        driver_qs = Member.drivers.all()
        merchant_id = self.context['bulk'].merchant_id
        if merchant_id:
            driver_qs = driver_qs.filter(merchant_id=merchant_id)

        driver = driver_qs.filter(Q(id=value) | Q(member_id=value)).first()
        if driver is None:
            raise serializers.ValidationError('Driver not found')
        return driver

    def validate_capacity(self, value):
        if value < 0:
            raise serializers.ValidationError('The capacity must be at least zero')
        return value

    def validate_breaks(self, value):
        breaks = []
        for schedule_break in value:
            if not schedule_break:
                continue
            if ('start' in schedule_break) != ('end' in schedule_break):
                raise serializers.ValidationError('You must provide start and end of break.')
            if not (schedule_break['start'] < schedule_break['end']):
                raise serializers.ValidationError('The end of the break must be after the start of the break.')
            breaks.append(schedule_break)

        breaks.sort(key=lambda b: b['start'])
        for index in range(len(breaks) - 1):
            if breaks[index]['end'] >= breaks[index + 1]['start']:
                raise serializers.ValidationError(_('Break ranges overlap.'), code='overlap_breaks')

        return breaks

    def validate_schedule(self, schedule):
        if schedule.get('day_off', False) is True:
            if ('start' in schedule) and ('end' in schedule):
                raise serializers.ValidationError(
                    'You cannot set schedule and mark day as day-off at the same time.'
                )
            if 'breaks' in schedule:
                raise serializers.ValidationError(
                    'You cannot set breaks and mark day as day-off at the same time.'
                )

        if ('start' in schedule) != ('end' in schedule):
            raise serializers.ValidationError('There must be both the start and the end of the shift')

        if ('start' in schedule) and ('end' in schedule):
            if not (schedule['start'] < schedule['end']):
                raise serializers.ValidationError('The end of the shift must be after the start of the shift.')
            schedule['day_off'] = False

        if 'breaks' in schedule:
            breaks = self.validate_breaks(schedule['breaks'].values())
            if breaks:
                schedule['breaks'] = breaks
                schedule['day_off'] = False
            else:
                del schedule['breaks']

        if schedule == {'day_off': False}:
            raise serializers.ValidationError(
                'You must provide start and end of shift for day marked as workday.'
            )

        return schedule

    def validate(self, attrs):
        if 'schedule' in attrs:
            attrs['schedule'] = self.validate_schedule(attrs['schedule'])
            if not attrs['schedule']:
                del attrs['schedule']

        if 'driver' in attrs and 'schedule' in attrs and 'breaks' in attrs['schedule']:
            from schedule.models import Schedule
            schedule_obj = Schedule.objects.get_or_create(member=attrs['driver'])[0]
            final_schedule = {
                **schedule_obj.schedule['constant'][self.context['target_date'].weekday()],
                **attrs['schedule'],
            }
            if final_schedule['start'] >= final_schedule['breaks'][0]['start']:
                raise serializers.ValidationError(_('The break went beyond working hours.'))
            if final_schedule['breaks'][-1]['end'] >= final_schedule['end']:
                raise serializers.ValidationError(_('The break went beyond working hours.'))

        return attrs


class DriverCSVMapper(PandasReadMapper):
    serializer_class = CSVReadDriverSerializer

    @property
    def unknown_columns(self):
        return self.field_validators[HeaderControl].unknown_fields

    @property
    def optional_missing(self):
        return self.field_validators[HeaderControl].optional_missing

    @property
    def serializer(self):
        return self.serializer_class()

    def __call__(self, value):
        row_data = super().__call__(value)
        serializer = self.serializer_class(data=list(row_data), many=True)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data


class DriverCSVParser(CSVModelMappingReader):
    mapper_class = DriverCSVMapper
    backend = PandasCSVBackend()


class MemberBulkScheduleUploadResultSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    member_id = serializers.IntegerField()
    full_name = serializers.CharField()


class DailyScheduleBreaksUploadSerializer(serializers.Serializer):
    start = serializers.TimeField(required=False, format='%H:%M')
    end = serializers.TimeField(required=False, format='%H:%M')


class DailyScheduleUploadSerializer(serializers.Serializer):
    start = serializers.TimeField(required=False, format='%H:%M')
    end = serializers.TimeField(required=False, format='%H:%M')
    day_off = serializers.BooleanField(default=False)
    breaks = DailyScheduleBreaksUploadSerializer(many=True, required=False)


class BulkScheduleUploadResultSerializer(serializers.Serializer):
    line = serializers.IntegerField()
    driver = MemberBulkScheduleUploadResultSerializer()
    capacity = serializers.FloatField(required=False)
    schedule = DailyScheduleUploadSerializer(required=False)
