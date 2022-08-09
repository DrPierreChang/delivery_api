# TODO: Attention: live patching of internal methods. I don't know why but urllib2 is not working - setting
# connection is never ending. But requests works fine. BTW, pyfcm lib also uses requests.
# If you have enough time fix it.
import requests
from push_notifications import gcm
from push_notifications.conf import get_manager


def send_message_factory(cl_type):
    def send_message(data, content_type, application_id):
        key = getattr(get_manager(), 'get_{}_api_key'.format(cl_type.lower()))(application_id)

        headers = {
            "Content-Type": content_type,
            "Authorization": "key=%s" % (key),
            "Content-Length": str(len(data)),
        }
        timeout = get_manager().get_error_timeout(cl_type, application_id) or None
        return requests.post(get_manager().get_post_url(cl_type, application_id),
                             data=data, headers=headers, timeout=timeout).content

    return send_message


for cl_type in ('FCM', 'GCM'):
    setattr(gcm, '_{}_send'.format(cl_type.lower()), send_message_factory(cl_type))

send_message = gcm.send_message
send_bulk_message = send_message
GCMError = gcm.GCMError
