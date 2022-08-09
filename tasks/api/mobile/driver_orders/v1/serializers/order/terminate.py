from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from radaro_utils.serializers.mobile.fields import NullResultMixin
from radaro_utils.serializers.mobile.serializers import RadaroMobileListSerializer, RadaroMobileModelSerializer
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order, TerminateCode

from ..fields import CustomKeyWithMerchantRelatedField


class TerminateCodeNumberSerializer(serializers.ModelSerializer):
    class Meta:
        model = TerminateCode
        list_serializer_class = RadaroMobileListSerializer
        fields = ('code', 'name', 'type', 'is_comment_necessary')


class TerminateCodesSerializer(NullResultMixin, RadaroMobileModelSerializer):
    codes = TerminateCodeNumberSerializer(many=True, source='terminate_codes', required=False, read_only=True)
    code_ids = CustomKeyWithMerchantRelatedField(
        source='terminate_codes',
        queryset=TerminateCode.objects.all(),
        required=False,
        write_only=True,
        many=True,
        key_field='code',
    )

    class Meta:
        model = Order
        fields = ('codes', 'code_ids', 'comment')
        extra_kwargs = {
            'comment': {'source': 'terminate_comment'},
        }

    def validate(self, attrs):
        order = self.parent.instance
        codes = attrs.get('terminate_codes', [])
        comment = attrs.get('terminate_comment', order.terminate_comment)

        if comment and not codes:
            raise serializers.ValidationError(
                {'comment': _('You can not send a comment without a code')},
                code='invalid_completion',
            )

        if not order.merchant.advanced_completion_enabled:
            for code in codes:
                if code.type == TerminateCode.TYPE_SUCCESS:
                    raise serializers.ValidationError(
                        {'code_ids': _('Success codes are disabled for your merchant.')},
                        code='invalid_completion',
                    )

        for code in codes:
            if code.is_comment_necessary and not comment:
                raise serializers.ValidationError(
                    {'comment': _('{code_type} comment is required.'.format(code_type=code.type.title()))},
                    code='required_completion_comment',
                )
        return attrs


class TerminateOrderMixinSerializer(serializers.ModelSerializer):
    completion = TerminateCodesSerializer(required=False, source='*')

    class Meta:
        model = Order
        fields = ['completion']
        abstract = True

    def validate(self, attrs):
        status = attrs.get('status', self.instance.status if self.instance else None)
        terminate_codes = attrs.get('terminate_codes', [])

        for code in terminate_codes:
            if code.type == TerminateCode.TYPE_ERROR and not status == OrderStatus.FAILED:
                raise serializers.ValidationError(
                    {'completion': _('You can not pass {code_type} code with this status.'
                                     .format(code_type=code.type))},
                    code='invalid_status_for_error_completion',
                )

            elif code.type == TerminateCode.TYPE_SUCCESS and not self.instance.can_confirm_with_status(status):
                raise serializers.ValidationError(
                    {'completion': _('You can not pass {code_type} code with this status.'
                                     .format(code_type=code.type))},
                    code='invalid_status_for_success_completion',
                )

        merchant = attrs.get('merchant', self.instance.merchant if self.instance else None)
        if 'status' in attrs and merchant.advanced_completion == merchant.ADVANCED_COMPLETION_REQUIRED:
            status = attrs['status']
            terminate_codes_required = (
                status == OrderStatus.WAY_BACK
                or (status == OrderStatus.DELIVERED and getattr(self.instance, 'status') != OrderStatus.WAY_BACK)
            )
            if terminate_codes_required and not self.is_terminate(attrs):
                raise serializers.ValidationError(
                    {'status': _('You cannot change the status before sending a terminate code')},
                    code='required_terminate_code',
                )

        return super().validate(attrs)

    def is_terminate(self, attrs=None):
        if (attrs and attrs.get('terminate_codes')) or self.instance.terminate_codes.exists():
            return True
        return False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not (isinstance(self.instance, Order) and not self.is_terminate()):
            self.fields['completion'].read_only = True
