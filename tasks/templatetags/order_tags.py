from django import template

from tasks.models import Order

register = template.Library()


@register.simple_tag(takes_context=True)
def job_status(context):
    order = context['original']
    return order.show_customer_tracking_page()


@register.simple_tag(takes_context=True)
def job_path(context):
    order = context['original']
    return order.status in [Order.DELIVERED, ] and order.real_path
