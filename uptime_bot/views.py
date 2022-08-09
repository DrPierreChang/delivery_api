import json
from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .celery_tasks import send_pong_to_uptimebot


@require_POST
@csrf_exempt
def ping(request):
    event = json.loads(request.body)
    event_type = event['type']

    if event_type == 'url_verification':
        return HttpResponse(event['challenge'])

    if event['verification_token'] != settings.UPTIME_BOT_VERIFICATION_TOKEN:
        return HttpResponse(status=401)

    if event_type == 'ping':
        send_pong_to_uptimebot.apply_async(
            (event['pong_url'], ),
            eta=timezone.now() + timedelta(seconds=event['service_delay']))

    return HttpResponse(status=200)
