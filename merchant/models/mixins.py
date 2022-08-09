from model_utils import Choices

from notification.models.mixins import SendNotificationMixin


class MerchantSendNotificationMixin(SendNotificationMixin):

    def _get_sender(self):
        sender = super(MerchantSendNotificationMixin, self)._get_sender()
        return self.merchant.sms_sender or sender


class MerchantTypes(object):
    MERCHANT_TYPES = Choices(
        ('DEFAULT', 'Default'),
        ('NTI', 'NTI'),
        ('MIELE_SURVEY', 'Miele Survey Merchant'),
        ('MIELE_DEFAULT', 'Miele Delivery/Service Merchant')
    )
