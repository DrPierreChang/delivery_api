from datetime import timedelta

from django import forms
from django.forms.utils import ErrorList
from django.utils.translation import ugettext_lazy as _

from ...fields import default_schedule_dict
from ...utils import str_to_breaks, str_to_time
from .const_schedule import ConstScheduleWidget, ConstScheduleWidgetField
from .one_time_schedule import OneTimeScheduleWidget, OneTimeScheduleWidgetField


class ScheduleWidget(forms.MultiWidget):
    error_messages = {
        'both_required': _('There must be both values.'),
        'invalid_range': _('The start time should be less than the end time.'),
        'invalid': _('Invalid data.'),
        'invalid_break_range': _('The start of the break must be before the end.'),
        'overlap_breaks': _('Break ranges overlap.'),
        'break_outside_schedule': _('The break went beyond working hours.'),
        'day_off_break': _("You can't add a weekend break."),
    }

    def __init__(self, today, attrs=None):
        self.today = today
        widgets = [
            forms.DateInput(attrs={'hidden': True, 'readonly': True}),
            ConstScheduleWidget,
            OneTimeScheduleWidget(today=today),
        ]

        super().__init__(widgets=widgets, attrs=attrs)

    def decompress(self, value):
        return self.today, value['constant'], value['one_time']

    def get_context(self, name, value, attrs):
        context = super().get_context(name=name, value=value, attrs=attrs)
        for type_schedule_key, type_schedule_errors in self.attrs['validation_errors_fired'].items():
            for daily_schedule_key, daily_schedule_errors in type_schedule_errors.items():
                widget = context['widget']['subwidgets'][type_schedule_key]['subwidgets'][daily_schedule_key]
                widget['errors'] = ErrorList([self.error_messages[daily_schedule_errors]])

        return context


class ScheduleWidgetField(forms.MultiValueField):
    default_error_messages = {
        'invalid': _('Invalid data.'),
    }

    def __init__(self, instance, *args, **kwargs):
        today = instance.today
        self.widget = ScheduleWidget(today=today)

        fields = [
            forms.DateField(),
            ConstScheduleWidgetField(),
            OneTimeScheduleWidgetField(today=today),
        ]
        self.validation_errors_fired = {}

        super().__init__(fields=fields, *args, **kwargs)

    def compress(self, data_list):
        if not data_list:
            return default_schedule_dict()

        onetime = {
            data_list[0] + timedelta(days=day_number): daily_schedule
            for day_number, daily_schedule in data_list[2].items()
        }
        return {'constant': data_list[1], 'one_time': onetime, 'today': data_list[0]}

    def _prepare_daily_schedule(self, daily_schedule):
        try:
            if 'start' in daily_schedule:
                daily_schedule['start'] = str_to_time(daily_schedule['start'])
            if 'end' in daily_schedule:
                daily_schedule['end'] = str_to_time(daily_schedule['end'])
            if 'breaks' in daily_schedule:
                daily_schedule['breaks'] = str_to_breaks(daily_schedule['breaks'])
        except ValueError:
            return 'invalid'

        return None

    def _validate_daily_schedule(self, daily_schedule):
        if daily_schedule.get('breaks', []):
            breaks = daily_schedule['breaks']

            if daily_schedule.get('day_off', False):
                return 'day_off_break'

            for one_break in breaks:
                if one_break['start'] >= one_break['end']:
                    return 'invalid_break_range'

            for index in range(len(breaks) - 1):
                if breaks[index]['end'] >= breaks[index + 1]['start']:
                    return 'overlap_breaks'

        if ('start' in daily_schedule) and ('end' in daily_schedule):
            if daily_schedule['start'] >= daily_schedule['end']:
                return 'invalid_range'

            if daily_schedule.get('breaks', []):
                if daily_schedule['start'] >= daily_schedule['breaks'][0]['start']:
                    return 'break_outside_schedule'
                if daily_schedule['breaks'][-1]['end'] >= daily_schedule['end']:
                    return 'break_outside_schedule'

        return None

    def validate(self, value):
        constant_errors = {}
        for weekday_number, daily_schedule in value['constant'].items():
            error_code = self._prepare_daily_schedule(daily_schedule)
            if error_code:
                constant_errors[weekday_number] = error_code
                continue

            if 'start' not in daily_schedule and 'end' not in daily_schedule:
                constant_errors[weekday_number] = 'both_required'
                continue

            error_code = self._validate_daily_schedule(daily_schedule)
            if error_code:
                constant_errors[weekday_number] = error_code
                continue

        one_time_errors = {}
        for day, daily_schedule in value['one_time'].items():
            if not daily_schedule:
                continue
            index = (day - value['today']).days

            error_code = self._prepare_daily_schedule(daily_schedule)
            if error_code:
                one_time_errors[index] = error_code
                continue

            if ('start' in daily_schedule) != ('end' in daily_schedule):
                one_time_errors[index] = 'both_required'
                continue

            validated_daily_schedule = {**value['constant'][day.weekday()], **daily_schedule}
            error_code = self._validate_daily_schedule(validated_daily_schedule)
            if error_code:
                one_time_errors[index] = error_code
                continue

        if constant_errors:
            self.validation_errors_fired[1] = constant_errors
        if one_time_errors:
            self.validation_errors_fired[2] = one_time_errors

        if self.validation_errors_fired:
            raise forms.ValidationError(self.error_messages['invalid'])

        del value['today']
        return super().validate(value)

    def widget_attrs(self, widget):
        attrs = super().widget_attrs(widget)
        attrs['validation_errors_fired'] = self.validation_errors_fired
        return attrs
