from merchant.models import SkillSet
from radaro_utils.serializers.mobile.serializers import RadaroMobileListSerializer, RadaroMobileModelSerializer


class SkillSetSerializer(RadaroMobileModelSerializer):
    class Meta:
        list_serializer_class = RadaroMobileListSerializer
        model = SkillSet
        fields = ('id', 'name', 'color', 'is_secret', 'description')
