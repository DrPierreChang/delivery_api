from datetime import timedelta

from django.utils import timezone

from push_notifications.conf import legacy


class PushNotificationsConfig(legacy.LegacyConfig):
    _app_configs = {}

    def _load_merchant_config(self, application_id):
        def get_app_config(app_id):
            from .models import PushNotificationsSettings

            conf = PushNotificationsSettings.objects.get(id=app_id)
            self._app_configs[app_id] = {'conf': conf, 'timeout': timezone.now() + timedelta(seconds=60)}
            return conf

        conf = self._app_configs.get(application_id, None)
        if not conf or conf['timeout'] < timezone.now():
            return get_app_config(application_id)
        return conf['conf']

    def get_apns_topic(self, application_id=None):
        if not application_id:
            return super(PushNotificationsConfig, self).get_apns_topic(None)
        else:
            conf = self._load_merchant_config(application_id)
            return conf.apns_topic

    def get_apns_certificate(self, application_id=None):
        return super(PushNotificationsConfig, self).get_apns_certificate(None)

    def get_apns_use_sandbox(self, application_id=None):
        return super(PushNotificationsConfig, self).get_apns_use_sandbox(None)

    def get_apns_use_alternative_port(self, application_id=None):
        if not application_id:
            return super(PushNotificationsConfig, self).get_apns_use_alternative_port(application_id)

    def get_fcm_api_key(self, application_id=None):
        if not application_id:
            return super(PushNotificationsConfig, self).get_fcm_api_key(application_id)
        else:
            conf = self._load_merchant_config(application_id)
            return conf.fcm_key

    def get_gcm_api_key(self, application_id=None):
        if not application_id:
            return super(PushNotificationsConfig, self).get_gcm_api_key(application_id)
        else:
            conf = self._load_merchant_config(application_id)
            return conf.gcm_key

    def get_wns_package_security_id(self, application_id=None):
        if not application_id:
            return super(PushNotificationsConfig, self).get_wns_package_security_id(application_id)

    def get_wns_secret_key(self, application_id=None):
        if not application_id:
            return super(PushNotificationsConfig, self).get_wns_secret_key(application_id)

    def get_post_url(self, cloud_type, application_id=None):
        if not application_id:
            return super(PushNotificationsConfig, self).get_post_url(cloud_type, application_id)
        else:
            conf = self._load_merchant_config(application_id)
            return getattr(conf, cloud_type.lower() + '_post_url')

    def get_error_timeout(self, cloud_type, application_id=None):
        if not application_id:
            return super(PushNotificationsConfig, self).get_error_timeout(cloud_type, application_id)
        else:
            conf = self._load_merchant_config(application_id)
            return getattr(conf, cloud_type.lower() + '_error_timeout')

    def get_max_recipients(self, cloud_type, application_id=None):
        if not application_id:
            return super(PushNotificationsConfig, self).get_max_recipients(cloud_type, application_id)
        else:
            conf = self._load_merchant_config(application_id)
            return getattr(conf, cloud_type.lower() + '_max_recipients')
