from django.conf import settings

SMS_STATUSES = ['sent', 'failed', 'unknown']


class SMSStatus(object):

    def __init__(self):
        self.service_response = None
        self.status = None


class SMSMessage(object):

    def __init__(self, text=None, sender=None, phone_number=None, connection=None, encoding=None):
        self.text = text
        self.phone_number = phone_number
        self.sender = sender or settings.DEFAULT_SMS_SENDER
        self.connection = connection
        self.sent_at = None
        self.encoding = encoding or settings.DEFAULT_CHARSET
        self.sms_status = SMSStatus()

    def get_connection(self, fail_silently=False):
        from radaro_utils.radaro_notifications.sms import get_connection
        if not self.connection:
            self.connection = get_connection(fail_silently=fail_silently)
        return self.connection

    @property
    def message(self):
        return self.text.encode(self.encoding)

    @property
    def recipient(self):
        return self.phone_number.strip('+')

    @property
    def originator(self):
        return self.sender.encode(self.encoding)

    def send(self):
        if not self.phone_number:
            return 0
        return self.get_connection().send_messages([self])
