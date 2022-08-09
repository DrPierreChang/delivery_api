from django import template

register = template.Library()


@register.simple_tag
def get_field_value(obj, field_name):
    return obj[field_name]
