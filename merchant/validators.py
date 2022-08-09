from rest_framework.exceptions import ValidationError


class MerchantsOwnValidator(object):
    _message = 'Your merchant does not have {type} with id {id}'

    def __init__(self, object_type, merchant_field='merchant'):
        self.type = object_type
        self.merchant_field = merchant_field
        self.merchant = None

    def __call__(self, value, *args, **kwargs):
        if getattr(value, self.merchant_field) != self.merchant:
            raise ValidationError(self._message.format(id=value.id, type=self.type))

    def set_context(self, serializer_field):
        request = serializer_field.parent.context.get('request')
        if request and request.user:
            self.merchant = request.user.current_merchant
        if not self.merchant:
            raise ValidationError('No merchant from request')
