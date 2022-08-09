from django.contrib.auth import authenticate, get_user_model
from django.db.models import Q
from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers
from rest_framework.settings import api_settings

from custom_auth.api.legacy.fields import CaseInsensitiveCharField

AuthUserModel = get_user_model()


class DriverLoginSerializer(serializers.Serializer):
    username = CaseInsensitiveCharField()
    password = serializers.CharField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.context['stage'] == self.context['view'].stage.PREFETCH:
            self.fields['password'].required = False

    def is_valid_login(self, user, is_force, device_id):
        if not user or not user.is_driver:
            raise serializers.ValidationError({
                api_settings.NON_FIELD_ERRORS_KEY: [_("Invalid username or password.")]
            }, code='invalid_credentials')
        if not user.is_active:
            raise serializers.ValidationError({
                api_settings.NON_FIELD_ERRORS_KEY: [_("User inactive or deleted.")]
            }, code='inactive_user')
        if user.user_auth_tokens.filter(marked_for_delete=False).exists() \
                and user.device_set.filter(in_use=True).exists():
            if not is_force:
                raise serializers.ValidationError({
                    api_settings.NON_FIELD_ERRORS_KEY: [_("You're currently online on another device.")]
                }, code='has_active_session')
            user.on_force_login(device_id)

    def prefetch_user(self):
        user = None
        try:
            user = AuthUserModel.objects.get(Q(username=self.validated_data['username'])
                                             | Q(email=self.validated_data['username']))
        except AuthUserModel.DoesNotExist:
            pass
        return user

    def authenticate(self, is_force, device_id):
        user = authenticate(**self.validated_data)
        self.is_valid_login(user, is_force, device_id)
        return user
