from django.contrib.postgres.fields import ArrayField, CIEmailField
from django.core.exceptions import ValidationError
from django.db import models

from constance import config

from radaro_utils.files.utils import get_upload_path
from radaro_utils.models import ResizeImageMixin
from radaro_utils.radaro_phone.models import PhoneField
from radaro_utils.radaro_phone.utils import e164_phone_format, phone_is_valid

from ..utils import ReportsFrequencySettingsMixin
from .fields import SmsSenderField


class SubBranding(ResizeImageMixin, ReportsFrequencySettingsMixin, models.Model):
    untracked_for_events = ()

    name = models.CharField(max_length=255)
    logo = models.ImageField(null=True, upload_to=get_upload_path)
    store_url = models.URLField(default='http://www.example.com/', verbose_name='Custom “URL” redirect link')
    merchant = models.ForeignKey('Merchant', related_name='subbrandings', on_delete=models.CASCADE)
    phone = PhoneField(blank=True)
    sms_sender = SmsSenderField(max_length=15, default='')
    webhook_url = ArrayField(models.CharField(null=True, blank=True, max_length=500), default=list, blank=True, size=5)
    pod_email = CIEmailField(max_length=50, blank=True, help_text='Email to send proof of delivery')
    jobs_export_email = CIEmailField(max_length=50, blank=True)
    survey_export_email = CIEmailField(max_length=50, blank=True, help_text='Email to send survey export')
    customer_survey = models.ForeignKey(
        'merchant_extension.Survey', null=True, blank=True, on_delete=models.SET_NULL,
        verbose_name='Customer Survey', related_name='sub_brands'
    )

    class Meta:
        verbose_name = 'Sub-branding Merchant'
        verbose_name_plural = 'Sub-branding Merchants'
        ordering = ('name', )

    def __str__(self):
        return u"{name}".format(name=self.name)

    @staticmethod
    def autocomplete_search_fields():
        return 'name__icontains', 'id__iexact'

    @property
    def customer_survey_enabled(self):
        return bool(self.customer_survey_id)

    def clean_fields(self, exclude=None):
        if self.phone:
            try:
                phone_is_valid(self.phone, self.merchant.countries)
            except ValidationError as exc:
                raise ValidationError({'phone': [exc.message, ]})
        super(SubBranding, self).clean_fields(exclude)

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if self.phone:
            self.phone = e164_phone_format(self.phone, self.merchant.countries)
        if not self.sms_sender:
            self.sms_sender = self.name[:config.MAX_SMS_SENDER_LENGTH]
        super(SubBranding, self).save(force_insert, force_update, using, update_fields)


__all__ = ['SubBranding']
