# coding=utf-8
from django import template

from radaro_utils import helpers

register = template.Library()


@register.filter
def chunks(array, size):
    return helpers.chunks(array, size)


@register.filter
def lookup(value, arg):
    try:
        return value[arg]
    except (TypeError, IndexError, KeyError):
        return


@register.filter
def stylize_growth(value):
    if value is None:
        str_value, color = ' — ', 'gray'
    else:
        sign, color = ('-', 'red') if value < 0 else (('+', 'green') if value > 0 else ('', 'gray'))
        str_value = '%(sign)s%(value)d%%' % {'sign': sign, 'value': abs(value)}
    return {'color': color, 'value': str_value}
