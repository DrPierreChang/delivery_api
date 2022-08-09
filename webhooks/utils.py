from uuid import UUID


def get_client_ip(request):
    return request.META.get('HTTP_X_FORWARDED_FOR') or request.META.get('REMOTE_ADDR')


def validate_uuid4(uuid_string):
    try:
        val = UUID(uuid_string, version=4)
    except ValueError:
        return False
    return val
