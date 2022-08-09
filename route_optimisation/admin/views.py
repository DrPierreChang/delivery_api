import json
from typing import Iterable

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from route_optimisation.models import EngineRun, RouteOptimisation


@method_decorator(staff_member_required, name='dispatch')
class RORoutesView(TemplateView):
    template_name = 'admin/route_optimisation/route_optimisation/routes.html'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.route_optimisation_id = None

    def dispatch(self, request, *args, **kwargs):
        self.route_optimisation_id = kwargs.get('ro_id')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        route_optimisation = get_object_or_404(RouteOptimisation, id=self.route_optimisation_id)
        engines = route_optimisation.optimisation_log.log.get('engines')
        engines_data = []
        if engines:
            runs: Iterable[EngineRun] = EngineRun.objects.filter(id__in=engines.keys()).order_by('id')
            for run in runs:
                if run.result is None:
                    engines_data = []
                    break
                engines_data.append({
                    'id': run.id,
                    'params': run.engine_options.params.to_dict(),
                    'result': run.result.to_dict(),
                })
        context = super().get_context_data(**kwargs)
        context.update({
            'key': settings.GOOGLE_MAPS_V3_APIKEY,
            'clusters': json.dumps(engines_data),
        })
        return context


@method_decorator(staff_member_required, name='dispatch')
class ROClusteringView(TemplateView):
    template_name = 'admin/route_optimisation/route_optimisation/clustering.html'

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.route_optimisation_id = None

    def dispatch(self, request, *args, **kwargs):
        self.route_optimisation_id = kwargs.get('ro_id')
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        route_optimisation = get_object_or_404(RouteOptimisation, id=self.route_optimisation_id)
        engines = route_optimisation.optimisation_log.log.get('engines')
        engines_data = []
        if engines:
            runs: Iterable[EngineRun] = EngineRun.objects.filter(id__in=engines.keys()).order_by('id')
            for run in runs:
                engines_data.append({
                    'id': run.id,
                    'params': run.engine_options.params.to_dict(),
                })
        context = super().get_context_data(**kwargs)
        context.update({
            'key': settings.GOOGLE_MAPS_V3_APIKEY,
            'clusters': json.dumps(engines_data),
        })
        return context
