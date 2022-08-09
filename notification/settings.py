from django.conf import settings

PUSH_NOTIFICATIONS_SETTINGS = getattr(settings, "PUSH_NOTIFICATIONS_SETTINGS", {})

 # APNS
if settings.DEBUG:
    PUSH_NOTIFICATIONS_SETTINGS.setdefault("APNS_USE_SANDBOX", True)
else:
    PUSH_NOTIFICATIONS_SETTINGS.setdefault("APNS_USE_SANDBOX", False)
PUSH_NOTIFICATIONS_SETTINGS.setdefault("APNS_USE_ALTERNATIVE_PORT", False)

# WNS
PUSH_NOTIFICATIONS_SETTINGS.setdefault("WNS_PACKAGE_SECURITY_ID", None)
PUSH_NOTIFICATIONS_SETTINGS.setdefault("WNS_SECRET_KEY", None)
PUSH_NOTIFICATIONS_SETTINGS.setdefault(
    "WNS_ACCESS_URL", "https://login.live.com/accesstoken.srf"
)

# User model
PUSH_NOTIFICATIONS_SETTINGS.setdefault("USER_MODEL", settings.AUTH_USER_MODEL)

# API endpoint settings
PUSH_NOTIFICATIONS_SETTINGS.setdefault("UPDATE_ON_DUPLICATE_REG_ID", False)

__version__ = '2.0'
