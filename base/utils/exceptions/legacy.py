from rest_framework.views import exception_handler


def get_first_detail(detail):
    if isinstance(detail, dict):
        for item in detail.values():
            value = get_first_detail(item)
            if value:
                return value
    if isinstance(detail, list):
        for item in detail:
            value = get_first_detail(item)
            if value:
                return value
    return detail


def legacy_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response:
        if hasattr(response.data, 'get') and response.data.get('detail'):
            response.data.update({'errors': None})
        else:
            response.data = {'detail': get_first_detail(exc.detail), 'errors': exc.detail}

    return response
