from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from base.models import Invite, Member
from radaro_router.exceptions import RadaroRouterClientException
from radaro_utils.radaro_phone.serializers import RadaroPhoneField
from radaro_utils.radaro_phone.validators import UniquePhoneNumberValidation
from reporting.api.legacy.serializers.delta import DeltaSerializer
from reporting.model_mapping import serializer_map


class InviteSerializer(serializers.ModelSerializer):

    phone = RadaroPhoneField(validators=[UniquePhoneNumberValidation(queryset=Invite.objects.all()),
                                         UniquePhoneNumberValidation(queryset=Member.objects.all())])

    class Meta:
        model = Invite
        fields = ('id', 'phone', 'email', 'invited', 'position', 'first_name', 'last_name',)
        read_only_fields = ('id', 'invited',)

    def validate(self, attrs):
        try:
            Invite.check_instance(attrs)
        except RadaroRouterClientException as exc:
            raise ValidationError('Already registered.')
        return attrs


@serializer_map.register_serializer
class InviteDeltaSerializer(DeltaSerializer):
    class Meta(DeltaSerializer.Meta):
        model = Invite
