from __future__ import absolute_import

from django.conf import settings
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from merchant.models import Merchant
from tasks.models.terminate_code import TerminateCode


@receiver(pre_save, sender=Merchant)
def create_success_codes_for_changed_merchant(sender, instance, *args, **kwargs):
    if instance.pk:
        old_val = Merchant.objects.get(pk=instance.pk).advanced_completion_enabled
        new_val = instance.advanced_completion_enabled
        if new_val and not old_val:
            existed_codes = instance.terminate_codes(manager='success_codes').values_list('code', flat=True)
            success_codes = [TerminateCode(type=TerminateCode.TYPE_SUCCESS, merchant=instance, **kwargs)
                             for kwargs in settings.TERMINATE_CODES[TerminateCode.TYPE_SUCCESS]['DEFAULT_CODES']
                             if (kwargs['code'] not in existed_codes)]
            TerminateCode.objects.bulk_create(success_codes)


@receiver(post_save, sender=Merchant)
def create_codes_for_new_merchant(sender, instance, created, *args, **kwargs):
    if created:
        codes = [TerminateCode(type=TerminateCode.TYPE_ERROR, merchant=instance, **kwargs) for kwargs in
                 settings.TERMINATE_CODES['error']['DEFAULT_CODES']]
        TerminateCode.objects.bulk_create(codes)
        if instance.advanced_completion_enabled:
            success_codes = [TerminateCode(type=TerminateCode.TYPE_SUCCESS, merchant=instance, **kwargs) for kwargs in
                             settings.TERMINATE_CODES['success']['DEFAULT_CODES']]
            TerminateCode.objects.bulk_create(success_codes)


__all__ = ['create_success_codes_for_changed_merchant', 'create_codes_for_new_merchant']
