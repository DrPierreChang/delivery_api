from django import forms
from django.conf import settings
from django.forms.fields import ChoiceField, MultipleChoiceField
from django.templatetags.static import static

from constance import config

from base.models import Member
from merchant.fields.screen_text_field import ScreenTextField
from merchant.models import (
    DriverHub,
    Hub,
    Merchant,
    MerchantGroup,
    SubBranding,
    default_assigned_job_screen_text_dict,
    default_job_failure_screen_text_dict,
    default_not_assigned_job_screen_text_dict,
)
from merchant.models.mixins import MerchantTypes
from merchant_extension.models import EndOfDayChecklist, JobChecklist, StartOfDayChecklist
from radaro_utils.countries import countries as country_list


class CMSMerchantReportForm(forms.Form):
    date_from = forms.DateTimeField(
        widget=forms.DateInput(attrs={'class': 'datepicker'}),
    )
    date_to = forms.DateTimeField(
        widget=forms.DateInput(attrs={'class': 'datepicker'}),
    )
    merchant = forms.ModelChoiceField(queryset=Merchant.objects.all(), required=False)


def _country_choices_iter():
    allowed_countries = config.ALLOWED_COUNTRIES
    for code, country in country_list:
        if code in allowed_countries:
            yield (code, country)


class MerchantForm(forms.ModelForm):
    # If you get stuck on merchant change view, possibly, it is caused by some conflict of TimeZoneField and DjDT
    # Last successful combination DjDT 1.9.1 and Timezone Field 2.1
    distance_reversed = dict(map(reversed, Merchant.distance_aliases.items()))

    countries = MultipleChoiceField(widget=forms.CheckboxSelectMultiple, choices=_country_choices_iter)
    distance_show_in = ChoiceField(initial=lambda: MerchantForm.distance_reversed[settings.DEFAULT_DISTANCE_SHOW_IN],
                                   choices=Merchant.distances)
    date_format = ChoiceField(initial=lambda: settings.DEFAULT_DATE_FORMAT, choices=Merchant.date_formats)
    job_failure_screen_text = ScreenTextField(initial=default_job_failure_screen_text_dict)
    assigned_job_screen_text = ScreenTextField(initial=default_assigned_job_screen_text_dict)
    not_assigned_job_screen_text = ScreenTextField(initial=default_not_assigned_job_screen_text_dict)
    pickup_failure_screen_text = ScreenTextField(initial=default_job_failure_screen_text_dict)

    def __init__(self, *args, **kwargs):
        super(MerchantForm, self).__init__(*args, **kwargs)
        self.fields['checklist'].queryset = JobChecklist.objects.all()
        self.fields['sod_checklist'].queryset = StartOfDayChecklist.objects.all()
        self.fields['eod_checklist'].queryset = EndOfDayChecklist.objects.all()
        self.fields['webhook_url'].widget.attrs['class'] = 'vTextField'
        if self.instance.merchant_type not in [MerchantTypes.MERCHANT_TYPES.MIELE_DEFAULT,
                                               MerchantTypes.MERCHANT_TYPES.MIELE_SURVEY]:
            self.fields['survey_export_directory'].widget = forms.HiddenInput()

        queryset = self.fields['required_skill_sets_for_notify_orders'].queryset
        self.fields['required_skill_sets_for_notify_orders'].queryset = queryset.filter(merchant=self.instance)

    class Meta:
        model = Merchant
        fields = '__all__'
        widgets = {
            'signature_screen_text': forms.Textarea(attrs={'rows': 20}),
            'pre_inspection_signature_screen_text': forms.Textarea(attrs={'rows': 20}),
            'pickup_signature_screen_text': forms.Textarea(attrs={'rows': 20}),
            'pickup_pre_inspection_signature_screen_text': forms.Textarea(attrs={'rows': 20}),
            'job_failure_signature_screen_text': forms.Textarea(attrs={'rows': 20}),
        }


class MerchantGroupForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(MerchantGroupForm, self).__init__(*args, **kwargs)
        self.fields['core_merchant'].queryset = Merchant.objects.filter(merchant_group=self.instance)

    class Meta:
        model = MerchantGroup
        fields = '__all__'


class SubBrandingForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['webhook_url'].widget.attrs['class'] = 'vTextField'

    class Meta:
        model = SubBranding
        fields = '__all__'


class DriverHubForm(forms.ModelForm):
    merchant = forms.ModelChoiceField(queryset=Merchant.objects.all(), required=False)

    class Meta:
        model = DriverHub
        fields = ('merchant', 'hub', 'driver')

    class Media:
        js = (
            static('hub/driverHubAdmin.js'),
        )

    def __init__(self, *args, **kwargs):
        super(DriverHubForm, self).__init__(*args, **kwargs)
        if not (self.instance.pk or 'merchant' in self.data):
            self.fields['hub'].queryset = Hub.objects.none()
            self.fields['driver'].queryset = Member.objects.none()
        elif self.instance.pk:
            merchant = self.instance.hub.merchant
            self.fields['hub'].queryset = Hub.objects.filter(merchant=merchant)
            self.fields['driver'].queryset = Member.drivers.filter(merchant=merchant)
