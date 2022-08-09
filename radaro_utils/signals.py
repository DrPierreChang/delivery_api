from django.dispatch import Signal

google_api_request_event = Signal(providing_args=['api_name', 'options'])


post_admin_page_action = Signal(providing_args=[])
