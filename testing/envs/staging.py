from datetime import timedelta

from django.utils import timezone

BASE_URL = 'api.radaro.razortheory.com'

SETTINGS = {
    'url': BASE_URL,
    'manager': {
        'login': 'managerweb1@gmail.co',
        'password': 'Password1234',
        'default_job': {
            "comment": "This job is created by testing script.",
            "customer": {
                "email": "stas.k@razortheory.com",
                "name": "Radaro",
                "phone": ""
            },
            "deliver_address": {
                "address": '',
                "description": "",
                "location": '',
            },
            "deliver_before": str(timezone.now() + timedelta(hours=3)),
            "title": "Test job"
        },
        'default_driver': 425
    },
    'driver': {
        'login': 'driverweb3@gmail.co',
        'password': 'Password1234'
    }
}
