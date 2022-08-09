from django.conf import settings
from django.contrib.postgres.fields import CIEmailField
from django.db import models

from merchant.models import Merchant
from tasks.models.mixins import TerminateCodeSendNotification

SUCCESS_CODES_DISABLED_MSG = 'Success codes was disabled for this merchant'


class TerminateCodeConstants(object):
    TYPE_ERROR = 'error'
    TYPE_SUCCESS = 'success'
    TYPE_CHOICES = (
        (TYPE_ERROR, 'Error'),
        (TYPE_SUCCESS, 'Success'),
    )


class SuccessTerminateCodeManager(models.Manager):
    def get_queryset(self):
        return super(SuccessTerminateCodeManager, self).get_queryset().filter(type=TerminateCodeConstants.TYPE_SUCCESS)


class ErrorTerminateCodeManager(models.Manager):
    def get_queryset(self):
        return super(ErrorTerminateCodeManager, self).get_queryset().filter(type=TerminateCodeConstants.TYPE_ERROR)


class TerminateCode(TerminateCodeConstants, TerminateCodeSendNotification, models.Model):
    untracked_for_events = ()

    type = models.CharField(choices=TerminateCodeConstants.TYPE_CHOICES, max_length=7)
    code = models.PositiveSmallIntegerField(editable=False, blank=True)
    name = models.CharField(max_length=100)
    is_comment_necessary = models.BooleanField(default=False, editable=False)
    merchant = models.ForeignKey(Merchant, related_name='terminate_codes', on_delete=models.CASCADE)
    email_notification_recipient = CIEmailField(max_length=50, blank=True)

    objects = models.Manager()

    success_codes = SuccessTerminateCodeManager()
    error_codes = ErrorTerminateCodeManager()

    class Meta:
        ordering = ('code', )
        unique_together = (('code', 'merchant'),)

    def __str__(self):
        return '%s: %s %s' % (self.get_type_display(), self.code, self.name)

    def save(self, *args, **kwargs):
        if not self.id:
            self.code = self._get_next_code()
        super(TerminateCode, self).save(*args, **kwargs)

    def _get_next_code(self):
        code_type = self.type
        type_settings = settings.TERMINATE_CODES[code_type]
        used_codes = TerminateCode.objects\
            .filter(type=code_type, merchant_id=self.merchant_id)\
            .exclude(code=type_settings['OTHER'])\
            .order_by('-code')\
            .values_list('code', flat=True)
        not_used_codes = set(range(type_settings['STARTING'], type_settings['OTHER'])).difference(used_codes)
        if not_used_codes:
            return min(not_used_codes)
