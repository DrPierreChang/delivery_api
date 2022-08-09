from django.http import Http404
from django.utils.encoding import force_text
from django.utils.http import urlsafe_base64_decode

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from tasks.models import Order

from ..serializers import OrderCurrentLocationSerializer


class CurrentLocationMixin(viewsets.GenericViewSet):
    @action(detail=True)
    def location(self, request, **kwargs):
        instance = self.get_object()
        if instance.status == Order.IN_PROGRESS:
            instance.current_location = instance.driver.last_location
            return Response(OrderCurrentLocationSerializer(instance=instance).data)
        return Response(status=status.HTTP_404_NOT_FOUND)


class ObjectByUIDB64ApiBase(viewsets.GenericViewSet):
    permission_classes = [AllowAny]
    uidb64_lookup_viewset = None

    def __init__(self, **kwargs):
        super(ObjectByUIDB64ApiBase, self).__init__(**kwargs)
        self._object_id = None
        assert self.uidb64_lookup_viewset is not None, 'Set parent_view_set'

    def dispatch(self, request, *args, **kwargs):
        uidb64_lookup = '{parent_viewset_prefix}_{parent_lookup_field}'.format(
            parent_viewset_prefix=self.uidb64_lookup_viewset.url_router_lookup,
            parent_lookup_field=self.uidb64_lookup_viewset.lookup_field,
        )
        uidb64 = kwargs.get(uidb64_lookup)
        if uidb64:
            try:
                self._object_id = int(force_text(urlsafe_base64_decode(uidb64)))
            except (TypeError, ValueError):
                raise Http404

        return super(ObjectByUIDB64ApiBase, self).dispatch(request, *args, **kwargs)
