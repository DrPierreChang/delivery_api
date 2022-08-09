from radaro_utils.radaro_notifications.sms import get_sms_settings
from radaro_utils.radaro_notifications.sms.backends.base import BaseRequestPayload, BaseRequestSMSBackend


class SMSBackend(BaseRequestSMSBackend):

    service_name = 'Rawmobility'

    def __init__(self, **kwargs):
        self.user_name = get_sms_settings('user_name', kwargs=kwargs)
        self.password = get_sms_settings('password', kwargs=kwargs)
        self.originator = get_sms_settings('originator', kwargs=kwargs)
        self.route = get_sms_settings('route', kwargs=kwargs)

        api_url = get_sms_settings('api_url', kwargs=kwargs,
                                   default='http://apps.rawmobility.com/gateway/api/simple/MT')

        super(SMSBackend, self).__init__(api_url, **kwargs)

    def get_request_payload(self, sms_message):
        return RawmobilitySMSPayload(sms_message, self)


class RawmobilitySMSPayload(BaseRequestPayload):

    def init_payload(self):
        self.params = {
            'USER_NAME': self.backend.user_name,
            'PASSWORD': self.backend.password,
            'ROUTE': self.backend.route,
            'MESSAGE_TEXT': self.message.message,
            'RECIPIENT': self.message.recipient,
            'ORIGINATOR': self.message.originator or self.backend.originator
        }
