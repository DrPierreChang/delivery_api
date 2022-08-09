from django.conf import settings
from django.contrib.auth import get_user_model

from rest_framework import serializers

from radaro_utils.serializers.mobile.fields import NullResultMixin, RadaroMobilePhoneField
from radaro_utils.serializers.mobile.serializers import RadaroMobileModelSerializer


class NestedAvatarSerializer(NullResultMixin, serializers.Serializer):
    url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    def prepare_url(self, instance, url):
        if not url and (instance.is_driver or instance.is_manager):
            url = settings.STATIC_URL + settings.DEFAULT_DRIVER_ICON

        if url:
            request = self.context.get('request', None)
            if request:
                return request.build_absolute_uri(url)
            return url

        return None

    def get_url(self, instance):
        url = instance.avatar.url if instance.avatar else None
        return self.prepare_url(instance, url)

    def get_thumbnail_url(self, instance):
        thumbnail_url = instance.thumb_avatar_100x100
        return self.prepare_url(instance, thumbnail_url)


class ManagerSerializer(RadaroMobileModelSerializer):
    avatar = NestedAvatarSerializer(source='*')
    phone_number = RadaroMobilePhoneField(source='phone')

    class Meta:
        model = get_user_model()
        fields = ('id', 'first_name', 'last_name', 'avatar', 'phone_number')
