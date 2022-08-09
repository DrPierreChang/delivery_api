from django.db.models import Prefetch

from route_optimisation.const import RoutePointKind
from route_optimisation.models import RoutePoint

from ..v1.views import DailyOrdersViewSet
from .serializers import V2DailyOrdersSerializer


class V2DailyOrdersViewSet(DailyOrdersViewSet):
    serializer_class = V2DailyOrdersSerializer

    def get_route_optimisations_qs(self):
        qs = super().get_route_optimisations_qs()

        breaks_qs = RoutePoint.objects.all().filter(point_kind=RoutePointKind.BREAK)
        qs = qs.prefetch_related(
            Prefetch('points', to_attr='breaks', queryset=breaks_qs),
        )

        return qs
