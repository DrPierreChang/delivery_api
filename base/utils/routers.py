import copy

from rest_framework.routers import DefaultRouter as _DefaultRouter
from rest_framework.routers import SimpleRouter

from rest_framework_nested.routers import NestedSimpleRouter as _NestedSimpleRouter


class DefaultRouter(_DefaultRouter):
    def __init__(self):
        super(DefaultRouter, self).__init__()
        self.trailing_slash = '/?'


class NestedSimpleRouter(_NestedSimpleRouter):
    def __init__(self, *args, **kwargs):
        super(NestedSimpleRouter, self).__init__(*args, **kwargs)
        self.trailing_slash = '/?'


class BulkRouterMixin(object):
    """
        Map http methods to actions defined on the bulk mixins.
        """
    routes = copy.deepcopy(SimpleRouter.routes)
    routes[0].mapping.update({
        'put': 'bulk_update',
        'patch': 'partial_bulk_update',
        'delete': 'bulk_destroy',
    })


class BulkNestedRouter(BulkRouterMixin, NestedSimpleRouter):
    pass


class BulkRouter(BulkRouterMixin, DefaultRouter):
    pass
