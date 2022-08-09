from django import forms

from schedule.utils import breaks_to_str


class ConstDailyScheduleWidget(forms.MultiWidget):
    template_name = 'admin/const_daily_schedule.html'

    def __init__(self, attrs=None):
        widgets = (
            forms.TimeInput(attrs={'style': 'width: 100px'}, format='%H:%M'),
            forms.TimeInput(attrs={'style': 'width: 100px'}, format='%H:%M'),
            forms.CheckboxInput(attrs={'style': 'margin-left: 30px'}),
        )
        super().__init__(widgets, attrs)

    def decompress(self, value):
        return value.get('start', None), value.get('end', None), value.get('day_off', False)


class OneTimeDailyScheduleWidget(forms.MultiWidget):
    template_name = 'admin/onetime_daily_schedule.html'

    def __init__(self, attrs=None):
        widgets = (
            forms.TimeInput(attrs={'style': 'width: 100px'}, format='%H:%M'),
            forms.TimeInput(attrs={'style': 'width: 100px'}, format='%H:%M'),
            forms.CheckboxInput(attrs={'style': 'margin-left: 30px'}),
            forms.TextInput(attrs={'style': 'width: 500px; margin-left: 30px'}),
        )
        super().__init__(widgets, attrs)

    def decompress(self, value):
        breaks = value.get('breaks', '')
        breaks_str = breaks_to_str(breaks)
        return value.get('start', None), value.get('end', None), value.get('day_off', False), breaks_str


class ConstDailyScheduleWidgetField(forms.MultiValueField):
    widget = ConstDailyScheduleWidget

    def __init__(self, *args, **kwargs):
        fields = (
            forms.CharField(),
            forms.CharField(),
            forms.BooleanField(),
        )
        super().__init__(fields=fields, *args, **kwargs)

    def compress(self, data_list):
        return {'start': data_list[0], 'end': data_list[1], 'day_off': data_list[2]}


class OneTimeDailyScheduleWidgetField(forms.MultiValueField):
    widget = ConstDailyScheduleWidget

    def __init__(self, *args, **kwargs):
        fields = (
            forms.CharField(),
            forms.CharField(),
            forms.BooleanField(),
            forms.CharField(),
        )
        super().__init__(fields=fields, *args, **kwargs)

    def compress(self, data_list):
        return {'start': data_list[0], 'end': data_list[1], 'day_off': data_list[2], 'breaks': data_list[3]}
