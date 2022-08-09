from django.conf import settings

import requests
from requests import RequestException
from requests.auth import HTTPBasicAuth
from requests.utils import get_auth_from_url, urldefragauth

from delivery.celery import app
from merchant_extension.models import ResultChecklist
from route_optimisation.models import RouteOptimisation
from tasks.models import ConcatenatedOrder, Order
from webhooks.serializers import ExternalJobEventsSerializer

from .api.route_optimisation.v1.serializers.optimisation import ExternalRouteOptimisationEventsSerializer
from .models import MerchantWebhookEvent
from .serializers.external_checklists import (
    ExternalDailyChecklistEventsSerializer,
    ExternalJobChecklistEventsSerializer,
    ExternalJobChecklistEventsSerializerV2,
)
from .serializers.external_concatenated_orders import ExternalConcatenatedOrderEventsSerializer


def make_request(url, request_data):
    post_params = dict(
        url=url, json=request_data, timeout=settings.EXTERNAL_JOB_EVENT_TIMEOUT
    )
    url_auth = get_auth_from_url(url)
    if url_auth[0] and url_auth[1]:
        post_params['url'] = urldefragauth(url)
        post_params['auth'] = HTTPBasicAuth(*url_auth)
    return requests.post(**post_params)


@app.task()
def send_external_job_event(order_id, new_values, old_values, updated_at, event_type, topic):
    order = Order.all_objects.filter(order_id=order_id).first()
    if not order:
        return

    merchant, sub_brand = order.merchant, order.sub_branding
    data = ExternalJobEventsSerializer(instance={'token': merchant.webhook_verification_token,
                                                 'new_values': new_values,
                                                 'old_values': old_values,
                                                 'order_info': order,
                                                 'updated_at': updated_at,
                                                 'event_type': event_type,
                                                 'topic': topic}).data

    send_external_event(merchant, data, updated_at, topic, order, sub_brand)


@app.task()
def send_external_daily_checklist_event(result_checklist_id, updated_at, topic):
    result_checklist = ResultChecklist.objects.filter(id=result_checklist_id).first()
    if not result_checklist:
        return

    merchant = result_checklist.driver.current_merchant

    data = ExternalDailyChecklistEventsSerializer(instance={
        'token': merchant.webhook_verification_token,
        'topic': topic,
        'driver_info': result_checklist.driver,
        'result_checklist_info': result_checklist,
        'updated_at': updated_at,
    }).data

    send_external_event(merchant, data, updated_at, topic)


@app.task()
def send_external_job_checklist_event(result_checklist_id, updated_at, topic):
    result_checklist = ResultChecklist.objects.filter(id=result_checklist_id).first()
    if not result_checklist:
        return

    merchant = result_checklist.order.merchant
    sub_brand = result_checklist.order.sub_branding

    data = ExternalJobChecklistEventsSerializer(instance={
        'token': merchant.webhook_verification_token,
        'topic': topic,
        'job_info': result_checklist.order,
        'result_checklist_info': result_checklist,
        'updated_at': updated_at,
    }).data

    send_external_event(merchant, data, updated_at, topic, result_checklist.order, sub_brand)


@app.task()
def send_external_job_checklist_confirmation_event(result_checklist_id, updated_at, topic):
    result_checklist = ResultChecklist.objects.filter(id=result_checklist_id).first()
    if not result_checklist:
        return

    merchant = result_checklist.order.merchant
    sub_brand = result_checklist.order.sub_branding
    driver = result_checklist.order.driver

    data = ExternalJobChecklistEventsSerializerV2(instance={
        'token': merchant.webhook_verification_token,
        'topic': topic,
        'order_info': result_checklist.order,
        'result_checklist_info': result_checklist,
        'updated_at': updated_at,
        'last_location': driver.last_location if driver is not None else None,
    }).data

    send_external_event(merchant, data, updated_at, topic, result_checklist.order, sub_brand)


@app.task()
def send_external_optimisation_event(optimisation_id, updated_at, topic):
    optimisation = RouteOptimisation.objects.filter(pk=optimisation_id).first()
    if not optimisation:
        return

    merchant = optimisation.merchant

    data = ExternalRouteOptimisationEventsSerializer(instance={
        'updated_at': updated_at,
        'optimisation_info': optimisation,
        'token': merchant.webhook_verification_token,
        'topic': topic
    }).data

    send_external_event(merchant, data, updated_at, topic)


@app.task()
def send_external_concatenated_order_event(concatenated_order_id, updated_at, topic):
    concatenated_order = ConcatenatedOrder.objects.filter(pk=concatenated_order_id).first()
    if not concatenated_order:
        return
    merchant = concatenated_order.merchant

    data = ExternalConcatenatedOrderEventsSerializer(instance={
        'updated_at': updated_at,
        'concatenated_order_info': concatenated_order,
        'token': merchant.webhook_verification_token,
        'topic': topic
    }).data

    send_external_event(merchant, data, updated_at, topic)


def send_external_event(merchant, data, updated_at, topic, order=None, sub_brand=None):
    urls = set(merchant.webhook_url + (sub_brand.webhook_url if sub_brand else []))
    webhook_failed_times = merchant.webhook_failed_times

    for url in urls:
        if not url:
            continue

        webhook_event_data = {
            'merchant_id': merchant.id,
            'sub_branding': sub_brand,
            'request_data': data,
            'happened_at': updated_at,
            'webhook_url': url,
            'topic': topic,
            'order': order
        }

        try:
            resp = make_request(url, data)
            webhook_event_data.update({
                'elapsed_time': resp.elapsed,
                'response_status': resp.status_code,
                'response_text': resp.text,
            })
        except RequestException as ex:
            webhook_event_data.update({
                'exception_detail': str(ex),
            })
            webhook_failed_times += 1
        else:
            webhook_failed_times = 0
        finally:
            MerchantWebhookEvent.objects.create(**webhook_event_data)

    if webhook_failed_times != merchant.webhook_failed_times:
        merchant.webhook_failed_times = webhook_failed_times
        merchant.save(update_fields=['webhook_failed_times'])
