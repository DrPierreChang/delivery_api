from django import forms

from ..models import Schedule
from .fields import ScheduleWidgetField


class CreateScheduleForm(forms.ModelForm):

    class Meta:
        model = Schedule
        fields = ('member',)


class ScheduleForm(forms.ModelForm):

    class Meta:
        model = Schedule
        fields = ('member', 'schedule')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['schedule'] = ScheduleWidgetField(instance=kwargs['instance'], required=False)
