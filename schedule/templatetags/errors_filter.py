from django import template

register = template.Library()


@register.filter
def show_errors(line):
    if 'schedule' in line.fields:
        return False
    return True
