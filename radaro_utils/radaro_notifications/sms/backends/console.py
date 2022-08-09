import sys
import threading
from collections import namedtuple

from radaro_utils.radaro_notifications.sms.backends.base import BasePayload, BaseServiceSMSBackend


class SMSBackend(BaseServiceSMSBackend):

    service_name = 'Console'

    def __init__(self, **kwargs):
        self.stream = kwargs.pop('stream', sys.stdout)
        self._lock = threading.RLock()

        super(SMSBackend, self).__init__(**kwargs)

    def write_message(self, sms_message):
        self.stream.write(u'--FAKE SMS--\n{}\n{}'.format(sms_message.message, '-' * 12))
        self.stream.write('\n')

    def send_messages(self, sms_messages):
        """Write all messages to the stream in a thread-safe way."""
        if not sms_messages:
            return
        msg_count = 0
        with self._lock:
            for message in sms_messages:
                try:
                    sent = self._send(message)
                except Exception as exc:
                    if self.fail_silently:
                        sent = False
                    else:
                        raise exc
                if sent:
                    self.write_message(message)
                    self.stream.flush()
                    msg_count += 1

        return msg_count

    def get_request_payload(self, sms_message):
        return TestPayload(backend=self, message=sms_message)

    def send_to_service(self, payload):
        response = namedtuple('response', ('status_code', ))
        return response(200)


class TestPayload(BasePayload):

    def init_payload(self):
        self.params = {}
