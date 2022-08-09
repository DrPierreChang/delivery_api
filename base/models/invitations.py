from __future__ import unicode_literals

import os
import sys
import uuid

from django.contrib.auth.hashers import make_password
from django.contrib.postgres.fields import CIEmailField
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from constance import config

from base.mixins import TrackModelChangesMixin
from base.models import Car
from merchant.models.mixins import MerchantSendNotificationMixin
from notification.models import MerchantMessageTemplate
from radaro_router.mixins import RouterCheckInstanceMixin
from radaro_router.models import RadaroRouterRelationMixin
from radaro_utils.radaro_phone.models import PhoneField
from radaro_utils.radaro_phone.utils import e164_phone_format, phone_is_valid
from reporting.signals import send_create_event_signal

from .members import Member


class Invite(MerchantSendNotificationMixin, RouterCheckInstanceMixin, RadaroRouterRelationMixin,
             TrackModelChangesMixin, models.Model):
    default_template_name = 'invitations/invitation'
    view_name = 'invite_confirm'
    complete_invitation = 'invitations/complete_invitation'
    trackable_fields = ('phone', 'email')
    check_fields = ('email', 'phone')

    first_name = models.CharField(max_length=256, blank=True)
    last_name = models.CharField(max_length=256, blank=True)
    initiator = models.ForeignKey(Member, related_name='invitations', on_delete=models.CASCADE)
    timestamp = models.DateTimeField(auto_now_add=True)
    phone = PhoneField(unique=True)
    email = CIEmailField(max_length=50, unique=True)
    pin_code = models.CharField(max_length=20, blank=True, db_index=True)
    pin_code_timestamp = models.DateTimeField(null=True, blank=True)
    position = models.PositiveIntegerField(choices=Member.positions, default=Member.DRIVER)
    invited = models.ForeignKey(Member, null=True, blank=True, related_name='invited', on_delete=models.CASCADE)
    token = models.CharField(max_length=150, blank=True, db_index=True)
    merchant = models.ForeignKey('merchant.Merchant', on_delete=models.CASCADE)

    def clean_fields(self, exclude=None):
        if Member.objects.filter(email=self.email).exists():
            raise ValidationError({'email': ['Already registered.', ]})

        if 'phone' not in exclude and ('initiator' not in exclude or 'merchant' not in exclude):
            if 'merchant' not in exclude:
                merchant = self.merchant
            else:
                merchant = self.initiator.current_merchant

            try:
                phone_is_valid(phone=self.phone, regions=merchant.countries)
            except ValidationError as exc:
                raise ValidationError({'phone': [exc.message, ]})

        return super(Invite, self).clean_fields(exclude)

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        if self.merchant_id is None:
            self.merchant = self.initiator.current_merchant
        if self.position in (Member.ADMIN, Member.MANAGER) and not self.token:
            self.token = uuid.uuid4()
        if self.phone:
            self.phone = e164_phone_format(self.phone, self.merchant.countries)
        super(Invite, self).save(force_insert, force_update, using, update_fields)

    def create_driver_pin(self, **kwargs):
        pin_len = config.INVITE_PIN_LENGTH
        mod = 10 ** pin_len
        self.pin_code = str(int.from_bytes(os.urandom(pin_len), sys.byteorder) % mod)\
            .rjust(pin_len, '0')
        self.send_notification(
            template_type=MerchantMessageTemplate.COMPLETE_INVITATION,
            merchant_id=self.merchant.id,
            extra_context=kwargs
        )
        self.pin_code_timestamp = timezone.now()
        self.save()

    @property
    def full_name(self):
        return u'{} {}'.format(self.first_name, self.last_name)

    def save_driver(self, password):
        from reporting.models import Event

        new_user = Member.objects.create(first_name=self.first_name,
                                         last_name=self.last_name,
                                         phone=self.phone,
                                         email=self.email,
                                         role=self.position,
                                         merchant=self.merchant,
                                         password=make_password(password),
                                         is_confirmed=True,
                                         car=Car.objects.create()
                                         )
        self.pin_code = ''
        self.invited = new_user
        self.save()
        event = Event.generate_event(self,
                                     initiator=new_user,
                                     field='invited',
                                     new_value=new_user,
                                     object=self,
                                     event=Event.CHANGED)
        send_create_event_signal(events=[event])
        return new_user

    def get_invite_url(self):
        uid = urlsafe_base64_encode(force_bytes(self.pk))
        return reverse(self.view_name, kwargs={'uidb64': uid, 'token': self.token})

    @property
    def get_position(self):
        return self.get_position_display()

    def __str__(self):
        return u'{0} on {1}'.format(self.invited or self.email, self.timestamp)
