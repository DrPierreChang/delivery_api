from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.db.models import Q
from django.http import Http404
from django.utils.encoding import force_text
from django.utils.http import urlsafe_base64_decode
from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.settings import api_settings

from .fields import CaseInsensitiveCharField

AuthUserModel = get_user_model()


class LoginSerializer(serializers.Serializer):
    fail_login_message = ''

    def authenticate(self, roles, is_force):
        user = authenticate(**self.validated_data)
        if not (user and any([getattr(user, role) for role in roles])):
            raise serializers.ValidationError({
                api_settings.NON_FIELD_ERRORS_KEY: [self.fail_login_message],
            })
        has_active_login = user.user_auth_tokens.filter(marked_for_delete=False).exists()\
            and user.device_set.filter(in_use=True).exists()
        if not is_force and 'is_driver' in roles and has_active_login:
            raise serializers.ValidationError({
                api_settings.NON_FIELD_ERRORS_KEY: ["You're currently online on another device."],
            })
        if not user.is_active:
            raise serializers.ValidationError({
                api_settings.NON_FIELD_ERRORS_KEY: ["User inactive or deleted."],
            })
        return user

    def prefetch_user(self):
        user = None
        try:
            user = AuthUserModel.objects.get(Q(username=self.validated_data['username'])
                                             | Q(email=self.validated_data['username']))
        except AuthUserModel.DoesNotExist:
            pass
        return user


class UsernameLoginSerializer(LoginSerializer):
    username = CaseInsensitiveCharField()
    password = serializers.CharField()

    fail_login_message = 'Invalid username or password.'


class ResetPasswordByEmailSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)

    class Meta:
        fields = ['email']
        model = AuthUserModel

    def __init__(self, *args, **kwargs):
        super(ResetPasswordByEmailSerializer, self).__init__(*args, **kwargs)

    def validate_email(self, attrs):
        if not self.Meta.model.objects.filter(email=attrs).exists():
            raise ValidationError(_("User with such email doesn't exist."))
        return attrs

    def send_reset_password_email(self):
        try:
            user = self.Meta.model.objects.get(email=self.validated_data.get('email'))
        except self.Meta.model.DoesNotExist:
            return

        user.send_reset_password_email()


class PasswordRecoverySerializer(serializers.Serializer):
    new_password1 = serializers.CharField(max_length=128)
    new_password2 = serializers.CharField(max_length=128)
    uid = serializers.CharField(max_length=10)
    token = serializers.CharField(max_length=30)

    def validate_uid(self, value):
        user_model = get_user_model()
        try:
            uid = force_text(urlsafe_base64_decode(value))
        except (TypeError, ValueError):
                raise Http404
        if not user_model.objects.filter(pk=uid).exists():
            raise Http404
        return uid

    def validate(self, attrs):
        new_password1 = attrs.get('new_password1', None)
        new_password2 = attrs.get('new_password2', None)
        uid = attrs.get('uid', None)
        token = attrs.get('token', None)
        if not new_password1 == new_password2:
            raise ValidationError("Passwords don't match.")
        validate_password(new_password1)
        user = get_object_or_404(get_user_model(), pk=uid)
        token_generator = PasswordResetTokenGenerator()
        if not token_generator.check_token(user, token):
            raise Http404
        return attrs

    def save(self, **kwargs):
        data = self.validated_data
        user = get_object_or_404(get_user_model(), pk=data['uid'])
        user.set_password(data['new_password1'])
        user.save()
