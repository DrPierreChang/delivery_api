from django.utils import timezone

import requests

from radaro_utils.radaro_notifications.sms import get_sms_settings


class BaseSMSBackend(object):

    def __init__(self, fail_silently=False, **kwargs):
        self.fail_silently = fail_silently

    def send_messages(self, sms_messages):
        raise NotImplementedError

    def open(self):
        pass

    def close(self):
        pass

    def __enter__(self):
        try:
            self.open()
        except Exception:
            self.close()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class BaseServiceSMSBackend(BaseSMSBackend):

    def _send(self, sms_message):

        if not sms_message.phone_number:
            return

        payload = self.get_request_payload(sms_message)
        try:
            response = self.send_to_service(payload)
        except Exception as exc:
            if not self.fail_silently:
                raise exc
            return False
        sms_message.sms_status.sent_at = timezone.now()
        sms_message.sms_status.service_response = response
        return True

    def send_messages(self, sms_messages):
        if not sms_messages:
            return

        num_sent = 0
        created_session = self.open()
        try:
            for message in sms_messages:
                sent = self._send(message)
                if sent:
                    num_sent += 1
        finally:
            if created_session:
                self.close()
        return num_sent

    def get_request_payload(self, sms_message):
        raise NotImplementedError

    def send_to_service(self, payload):
        raise NotImplementedError


class BaseRequestSMSBackend(BaseServiceSMSBackend):

    def __init__(self, api_url, **kwargs):
        self.api_url = api_url
        self.timeout = get_sms_settings('service_timeout', default=5, kwargs=kwargs)
        super(BaseRequestSMSBackend, self).__init__(**kwargs)
        self.session = None

    def open(self):
        if self.session:
            return False
        try:
            self.session = requests.Session()
        except requests.RequestException:
            if not self.fail_silently:
                raise
            return False
        return True

    def close(self):
        if self.session is None:
            return
        try:
            self.session.close()
        except requests.RequestException:
            if not self.fail_silently:
                raise
        finally:
            self.session = None

    def _send(self, sms_message):
        if self.session is None:
            raise RuntimeError('Session is not opened')
        return super(BaseRequestSMSBackend, self)._send(sms_message)

    def send_to_service(self, payload):
        params = payload.get_request_params()
        params.setdefault('timeout', self.timeout)

        try:
            # raise requests.RequestException
            response = self.session.request(**params)
        except requests.RequestException as exc:
            exc_class = type('SMSBackendRequestError', (type(exc), ), {})
            raise exc_class('Error occurred during sending sms on url: {}'
                            .format(params.get('url', '<missing_url>')))
        return response


class BasePayload(object):

    def __init__(self, message, backend):
        self.message = message
        self.backend = backend
        self.service_name = backend.service_name

        self.init_payload()

    def init_payload(self):
        raise NotImplementedError


class BaseRequestPayload(BasePayload):

    def __init__(self, message, backend, method="POST",
                 params=None, data=None, headers=None, auth=None):
        self.method = method
        self.params = params
        self.data = data
        self.headers = headers
        self.auth = auth

        super(BaseRequestPayload, self).__init__(message, backend)

    def get_request_params(self):

        return dict(
            method=self.method,
            url=self.backend.api_url,
            params=self.params,
            data=self.serialize_data(),
            headers=self.headers,
            auth=self.auth,
        )

    def serialize_data(self):
        return self.data
