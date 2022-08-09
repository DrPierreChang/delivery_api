from django.conf import settings

from requests import ConnectionError

from radaro_router import RadaroRouterClient
from radaro_router.exceptions import RadaroRouterClientException


class RouterCheckInstanceMixin(object):
    check_fields = None

    @classmethod
    def check_instance(cls, query_params):
        client = RadaroRouterClient(token=settings.RADARO_ROUTER_TOKEN)
        try:
            method_name = "check_{model_name}_data".format(model_name=cls.__name__.lower())
            check = getattr(client, method_name)
            check(query_params)
        except RadaroRouterClientException as exc:
            raise exc
        except ConnectionError as exc:
            pass
