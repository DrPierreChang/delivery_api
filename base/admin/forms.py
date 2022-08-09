from copy import copy

from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.widgets import AdminDateWidget
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import transaction
from django.template import Context
from django.utils import timezone

import phonenumbers

from base.celery_tasks import weekly_usage_report
from base.models import CSVDriverSchedulesFile, DriverScheduleUpload, Invite, Member
from merchant.models import Merchant, SkillSet
from notification.models import MerchantMessageTemplate, TemplateSMSMessage
from radaro_router.exceptions import RadaroRouterClientException
from radaro_utils.radaro_admin.widgets import MerchantRawIdWidget


class PhoneNumberForm(forms.Form):
    phone = forms.CharField(help_text='Mobile phone number need to be entered in international formatting')

    def clean_phone(self):
        phone = self.cleaned_data['phone']

        if phone[0] != '+':
            phone = '+' + phone

        try:
            number = phonenumbers.parse(phone)
        except phonenumbers.NumberParseException as exc:
            raise forms.ValidationError(exc.args[0])
        if not phonenumbers.is_valid_number(number):
            raise forms.ValidationError("Invalid phone number")

        return phone

    def send_sms(self):
        template = MerchantMessageTemplate.objects.get(
            template_type=MerchantMessageTemplate.ANOTHER,
            merchant__isnull=True
        )
        context = Context({'time': timezone.now()})
        message = TemplateSMSMessage.objects.create(phone=self.cleaned_data['phone'],
                                                    template=template, context=context)
        message.send()


class CMSWeeklyUsageReportForm(forms.Form):
    report_date = forms.DateTimeField(widget=forms.DateInput(attrs={'class': 'datepicker'}), initial=timezone.now())
    email = forms.EmailField(widget=forms.EmailInput(attrs={'size': '20'}))

    def send_email(self):
        callback = lambda: weekly_usage_report.delay(report_date=self.cleaned_data['report_date'],
                                                     emails=[self.cleaned_data['email'], ])
        callback() if settings.TESTING_MODE else transaction.on_commit(callback)


def validate_not_earlier_than_now(date):
    yesterday = timezone.now().date() - timezone.timedelta(days=1)
    if date < yesterday:
        raise ValidationError('You cannot specify a past date')


class DriverScheduleImportForm(forms.Form):
    required_css_class = 'required'

    date = forms.DateField(widget=AdminDateWidget(), validators=[validate_not_earlier_than_now])
    file = forms.FileField(validators=[FileExtensionValidator(allowed_extensions=['csv'])])

    def save_schedule(self, request):
        csv_file = self.cleaned_data['file']
        date = self.cleaned_data['date']

        bulk = DriverScheduleUpload.objects.create(
            creator=request.user,
            method=DriverScheduleUpload.ADMIN,
            uploaded_from=request.headers.get('user-agent', '')
        )
        CSVDriverSchedulesFile.objects.create(file=csv_file, target_date=date, bulk=bulk)
        bulk.prepare_file()
        return bulk


class CheckInstanceUniqueness(object):

    def clean(self):
        cleaned_data = copy(super(CheckInstanceUniqueness, self).clean())

        if not self.instance.check_fields:
            return cleaned_data

        try:
            query_params = {key: value for key, value in cleaned_data.items() if key in self.instance.check_fields}

            if self.instance.radaro_router and self.instance.radaro_router.remote_id:
                query_params['remote_id'] = self.instance.radaro_router.remote_id
            self.instance.check_instance(query_params)
        except RadaroRouterClientException as exc:
            errors = exc.errors.get('errors', '')
            if isinstance(errors, dict):
                common_error = errors.pop('non_field_errors', None)
                if common_error:
                    raise ValidationError(common_error)
                for key, value in errors.items():
                    self.add_error(key, value[0])
            else:
                raise ValidationError(errors)
            self.cleaned_data = cleaned_data

        return cleaned_data


class InviteCreationForm(CheckInstanceUniqueness, forms.ModelForm):
    merchant = forms.ModelChoiceField(
        queryset=Merchant.objects.all(), required=False,
        help_text='If you do not select a merchant, the merchant of the initiator will be selected.',
    )

    class Meta:
        model = Invite
        fields = '__all__'


class MemberCreationForm(CheckInstanceUniqueness, UserCreationForm):

    class Meta(UserCreationForm.Meta):
        model = Member
        fields = ("username", "email", "phone")


class MemberChangeForm(CheckInstanceUniqueness, UserChangeForm):

    def __init__(self, *args, **kwargs):
        super(MemberChangeForm, self).__init__(*args, **kwargs)
        if hasattr(self.instance, 'merchant'):
            merchant_id = self.instance.merchant_id
            self.fields['skill_sets'].queryset = SkillSet.objects.filter(merchant_id=merchant_id)

            # modification of raw_id_fields fields
            raw_id_fields = ('sub_branding', 'starting_hub', 'ending_hub')
            for field in raw_id_fields:
                self.fields[field].widget = MerchantRawIdWidget(
                    rel=self.instance._meta.get_field(field).remote_field,
                    admin_site=admin.site,
                    attrs={'object': self.instance}
                )

    def clean(self):
        if self.cleaned_data['role'] != Member.NOT_DEFINED and self.cleaned_data['merchant'] is None:
            raise ValidationError({'merchant': 'Merchant is required for this user.'})
        if self.cleaned_data['role'] in Member.ROLES_WITH_MANY_MERCHANTS and self.cleaned_data.get('merchants'):
            if not self.cleaned_data['merchants'].filter(id=self.cleaned_data['merchant'].id).exists():
                raise ValidationError({'merchants': 'The list must contain the main merchant of the member.'})

        return super(MemberChangeForm, self).clean()
