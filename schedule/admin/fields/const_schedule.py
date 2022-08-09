from django import forms
from django.utils.dates import WEEKDAYS
from django.utils.translation import ugettext_lazy as _

from .daily_schedule import ConstDailyScheduleWidget, ConstDailyScheduleWidgetField

WEEKDAY_FIELDS = [weekday_number for weekday_number in WEEKDAYS.keys()]


class ConstScheduleWidget(forms.MultiWidget):
    template_name = 'admin/const_schedule.html'

    def __init__(self, attrs=None):
        widgets = [ConstDailyScheduleWidget(attrs={'label_text': name}) for name in WEEKDAYS.values()]

        super().__init__(widgets=widgets, attrs=attrs)

    def decompress(self, value):
        return [value[field] for field in WEEKDAY_FIELDS]


class ConstScheduleWidgetField(forms.MultiValueField):
    widget = ConstScheduleWidget

    default_error_messages = {
        'required': _('The values in the constant schedule are required.'),
    }

    def __init__(self, *args, **kwargs):
        fields = [ConstDailyScheduleWidgetField(required=True) for _ in WEEKDAY_FIELDS]
        super().__init__(fields=fields, *args, **kwargs)

    def compress(self, data_list):
        return dict(zip(WEEKDAY_FIELDS, data_list))
