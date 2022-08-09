from django.utils.translation import gettext_lazy as _

from rest_framework import serializers

from radaro_router.exceptions import RadaroRouterClientException


class MemberUniqueValidator:
    instance = None

    def set_context(self, serializer):
        self.instance = getattr(serializer, 'instance', None)

    def __call__(self, attrs):
        new_email = attrs.get('email')
        if new_email is None:
            return

        check_params = {
            'email': new_email,
            'username': self.instance.username
        }
        if self.instance.radaro_router and self.instance.radaro_router.remote_id:
            check_params['remote_id'] = self.instance.radaro_router.remote_id

        try:
            self.instance.check_instance(check_params)
        except RadaroRouterClientException:
            raise serializers.ValidationError({'email': _('User with such email already registered.')})
