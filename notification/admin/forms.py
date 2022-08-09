from django import forms

from notification.models import Device, GCMDevice
from radaro_utils.utils import get_content_types_for


class DeviceForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        real_type_choices = ['notification.device', 'notification.apnsdevice', 'notification.gcmdevice', ]
        super(DeviceForm, self).__init__(*args, **kwargs)
        if 'real_type' in self.fields:
            self.fields['real_type'].queryset = get_content_types_for(real_type_choices)


class NotificationForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(NotificationForm, self).__init__(*args, **kwargs)
        self.fields['devices'].queryset = Device.objects.select_related('user')


def app_names():
    choices = GCMDevice.objects.exclude(app_name__isnull=True)
    choices = choices.values_list('app_name', flat=True).order_by('app_name').distinct()
    return [('', 'All')] + list(map(lambda choice: (choice, choice), choices))


class DeviceVersionReportForm(forms.Form):
    SHORT_REPORT = 'short'
    DETAILED_REPORT = 'detailed'
    _report_choices = (
        (SHORT_REPORT, 'Short'),
        (DETAILED_REPORT, 'Detailed'),
    )

    date_from = forms.DateTimeField(
        widget=forms.DateInput(attrs={'class': 'datepicker'}), label='Last ping term from', required=False
    )
    date_to = forms.DateTimeField(
        widget=forms.DateInput(attrs={'class': 'datepicker'}), label='Last ping term to', required=False,
    )
    report_type = forms.ChoiceField(choices=_report_choices, required=False)
    app_name = forms.ChoiceField(choices=app_names, required=False)
