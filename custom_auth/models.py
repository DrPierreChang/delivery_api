from __future__ import absolute_import

from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, UserManager
from django.contrib.auth.tokens import default_token_generator
from django.contrib.postgres.fields import CICharField, CIEmailField
from django.core import validators
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from notification.models import MerchantMessageTemplate
from notification.models.mixins import SendNotificationMixin


class PasswordTokenMixin(object):
    def _get_token_url(self, token_generator, reset_name):
        uid = urlsafe_base64_encode(force_bytes(self.pk))
        token = token_generator.make_token(self)
        return '/{0}/{1}/{2}?domain={3}'.format(reset_name, uid, token, settings.CURRENT_HOST)


class ResetPasswordMixin(PasswordTokenMixin, SendNotificationMixin, models.Model):
    reset_password_email_template = 'email/reset_password/reset_password'
    reset_name = 'reset'
    reset_password_token_generator = default_token_generator

    class Meta:
        abstract = True

    def get_password_reset_url(self):
        return self._get_token_url(self.reset_password_token_generator, self.reset_name)

    def send_reset_password_email(self):
        self.send_notification(send_sms=False, template_type=MerchantMessageTemplate.RESET_PASSWORD,
                               merchant_id=self.merchant_id)


class ConfirmAccountManagerMixin(object):
    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('is_confirmed', True)
        username = email
        return super(ConfirmAccountManagerMixin, self).create_superuser(username, email, password, **extra_fields)


class ConfirmAccountMixin(SendNotificationMixin, models.Model):
    confirm_account_email_template = 'email/confirm_account/confirm_account'
    confirm_account_token_generator = default_token_generator

    is_confirmed = models.BooleanField('confirmed', default=False,
                                       help_text='Designates whether this user confirm his account.')
    confirmation_email_sent = models.BooleanField(default=False,
                                                  help_text='Designates whether the confirmation email was sent.')

    class Meta:
        abstract = True

    def save(self, force_insert=False, force_update=False, using=None,
             update_fields=None):
        super(ConfirmAccountMixin, self).save(force_insert, force_update, using, update_fields)

        if not (self.is_confirmed or self.confirmation_email_sent) and getattr(self, 'need_email_confirmation', False):
            self.send_confirm_account_email()

    def get_confirm_account_url(self):
        uid = urlsafe_base64_encode(force_bytes(self.pk))
        token = self.confirm_account_token_generator.make_token(self)
        return reverse('account_confirm', kwargs={'uidb64': uid, 'token': token})

    def send_confirm_account_email(self):
        self.send_notification(send_sms=False, template_type=MerchantMessageTemplate.CONFIRM_ACCOUNT,
                               merchant_id=self.merchant_id)
        self.confirmation_email_sent = True
        self.save(update_fields=('confirmation_email_sent', ))


class ApplicationUserManager(ConfirmAccountManagerMixin, UserManager):
    pass


class ApplicationUser(AbstractBaseUser, PermissionsMixin, ResetPasswordMixin, ConfirmAccountMixin):

    username = CICharField(
        'username',
        max_length=256,
        unique=True,
        help_text='Required. 256 characters or fewer. Letters, digits and @/./+/-/_ only.',
        validators=[
            validators.RegexValidator(
                r'^[\w.@+-]+$',
                'Enter a valid username. This value may contain only '
                  'letters, numbers ' 'and @/./+/-/_ characters.'
            ),
        ],
        error_messages={
            'unique': "A user with that username already exists.",
        },
    )
    first_name = models.CharField('first name', max_length=30, blank=True)
    last_name = models.CharField('last name', max_length=30, blank=True)
    email = CIEmailField('email address', unique=True, blank=False, null=False)
    is_staff = models.BooleanField(
        'staff status',
        default=False,
        help_text='Designates whether the user can log into this admin site.',
    )
    is_active = models.BooleanField(
        'active',
        default=True,
        help_text='Designates whether this user should be treated as active. '
                  'Unselect this instead of deleting accounts.',
    )
    date_joined = models.DateTimeField('date joined', default=timezone.now)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = 'user'
        verbose_name_plural = 'users'
        abstract = True

    def get_full_name(self):
        """
        Returns the first_name plus the last_name, with a space in between.
        """
        full_name = '%s %s' % (self.first_name, self.last_name)
        return full_name.strip()

    @property
    def full_name(self):
        return self.get_full_name()

    def get_short_name(self):
        """
        Returns the short name for the user.
        """
        return self.first_name
