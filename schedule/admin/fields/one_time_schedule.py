from datetime import timedelta

from django import forms
from django.utils import timezone

from .daily_schedule import OneTimeDailyScheduleWidget, OneTimeDailyScheduleWidgetField

COUNT_ONETIME_DAYS = 8


class OneTimeScheduleWidget(forms.MultiWidget):
    template_name = 'admin/onetime_schedule.html'

    def __init__(self, today, attrs=None):
        days = []
        for day_number in range(0, COUNT_ONETIME_DAYS):
            day = today + timedelta(days=day_number)
            day_name = day.strftime('%d-%m-%Y (%a)')
            days.append((day, day_name))

        widgets = [OneTimeDailyScheduleWidget(attrs={'label_text': label}) for _, label in days]

        super().__init__(widgets=widgets, attrs=attrs)

    def decompress(self, value):
        result = []
        today = timezone.now().date()
        for day_number in range(0, COUNT_ONETIME_DAYS):
            day = today + timedelta(days=day_number)
            daily_schedule = value.get(day, None)
            if daily_schedule:
                result.append(daily_schedule)
            else:
                result.append({})

        return result


class OneTimeScheduleWidgetField(forms.MultiValueField):
    def __init__(self, today, *args, **kwargs):
        fields = [OneTimeDailyScheduleWidgetField() for _ in range(0, COUNT_ONETIME_DAYS)]
        self.widget = OneTimeScheduleWidget(today=today)
        super().__init__(fields=fields, *args, **kwargs)

    def compress(self, data_list):
        one_time_schedule = {}
        for day_number, daily_schedule in enumerate(data_list):
            for key in ['start', 'end', 'breaks']:
                if not daily_schedule[key]:
                    del daily_schedule[key]

            if daily_schedule != {'day_off': False}:
                one_time_schedule[day_number] = daily_schedule

        return one_time_schedule
