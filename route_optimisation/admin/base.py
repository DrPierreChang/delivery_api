from collections import OrderedDict

from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from django.utils.html import format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _

import pytz

from radaro_utils.radaro_admin.admin import RemoveDeleteActionMixin, Select2FiltersMixin
from route_optimisation.admin.forms import EngineRunForm, RouteOptimisationForm
from route_optimisation.models import (
    DriverRoute,
    DriverRouteLocation,
    EngineRun,
    OptimisationTask,
    RouteOptimisation,
    RoutePoint,
)
from routing.google import ApiName
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order


@admin.register(RouteOptimisation)
class RouteOptimisationAdmin(Select2FiltersMixin, admin.ModelAdmin):
    form = RouteOptimisationForm
    list_display = ('id', 'type', 'merchant', 'get_task_created_at', 'created_by', 'day', 'state', 'get_cost',)
    list_select_related = ('merchant', 'created_by', 'delayed_task')
    list_filter = ('merchant', 'state', 'type',)
    readonly_fields = ('get_google_api_requests', )
    exclude = ('google_api_requests', )
    change_form_template = 'admin/route_optimisation/route_optimisation/change_form.html'

    def get_cost(self, optimisation):
        return (optimisation.google_api_requests or {}).get('cost', '-')
    get_cost.short_description = _('Optimisation cost')

    def get_task_created_at(self, optimisation):
        task = getattr(optimisation, 'delayed_task', None)
        if task:
            return task.created.astimezone(pytz.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    get_task_created_at.short_description = 'Created at'

    def get_google_api_requests(self, optimisation):
        if not optimisation.google_api_requests:
            return mark_safe("<span class='errors'>No data</span>")
        result = OrderedDict((
            ('Cost', optimisation.google_api_requests.get('cost', '-')),
            ('"Directions Simple" requests', optimisation.google_api_requests.get(ApiName.DIRECTIONS, '-')),
            ('"Directions Advanced" requests', optimisation.google_api_requests.get(ApiName.DIRECTIONS_ADVANCED, '-')),
            ('"Distance Matrix Simple" elements', optimisation.google_api_requests.get(ApiName.DIMA, '-')),
        ))
        return format_html_join(mark_safe('<br>'), '{}: {}', ((key, value) for key, value in result.items()),)
    get_google_api_requests.short_description = 'Google API requests'

    def delete_and_unassign_action(self, request, queryset):
        order_ct = ContentType.objects.get_for_model(Order)
        for optimisation in queryset:
            if optimisation.state in (RouteOptimisation.STATE.VALIDATION, RouteOptimisation.STATE.OPTIMISING):
                optimisation.terminate(initiator=request.user, request=request)
                self.message_user(request, f'{optimisation} terminated and removed')
            else:
                orders_route_points = RoutePoint.objects\
                    .filter(point_content_type=order_ct, route__optimisation=optimisation)\
                    .values_list('point_object_id', flat=True)
                qs = Order.aggregated_objects.filter_by_merchant(optimisation.merchant)
                orders_before = qs.filter(id__in=orders_route_points, status=OrderStatus.ASSIGNED).count()
                optimisation.delete(unassign=True, initiator=request.user, cms_user=True, request=request)
                orders_after = qs.filter(id__in=orders_route_points, status=OrderStatus.ASSIGNED).count()
                unassigned_count = orders_before - orders_after
                message = '{} deleted'.format(str(optimisation))
                if unassigned_count:
                    message += ', {} orders unassigned'.format(unassigned_count)
                self.message_user(request, message)
        self.message_user(request, "Successfully done")
    delete_and_unassign_action.short_description = _("Soft delete selected optimisations and unassign jobs")

    def delete_and_keep_jobs_action(self, request, queryset):
        for optimisation in queryset:
            if optimisation.state in (RouteOptimisation.STATE.VALIDATION, RouteOptimisation.STATE.OPTIMISING):
                optimisation.terminate(initiator=request.user, request=request)
                self.message_user(request, f'{optimisation} terminated and removed')
            else:
                optimisation.delete(unassign=False, initiator=request.user, cms_user=True, request=request)
                self.message_user(request, '{} deleted'.format(str(optimisation)))
        self.message_user(request, "Successfully done")
    delete_and_keep_jobs_action.short_description = _("Soft delete selected optimisations, keep jobs assigned")

    def delete_model(self, request, obj):
        if obj.state in (RouteOptimisation.STATE.VALIDATION, RouteOptimisation.STATE.OPTIMISING):
            obj.terminate(initiator=request.user, request=request)
        obj.delete()

    def delete_queryset(self, request, queryset):
        for ro in queryset.filter(state__in=(RouteOptimisation.STATE.VALIDATION, RouteOptimisation.STATE.OPTIMISING)):
            ro.terminate(initiator=request.user, request=request)
        queryset.delete()

    actions = [delete_and_unassign_action, delete_and_keep_jobs_action]


@admin.register(DriverRoute)
class DriverRouteAdmin(RemoveDeleteActionMixin, Select2FiltersMixin, admin.ModelAdmin):
    list_display = ('optimisation', 'driver', 'total_time', 'driving_time', 'driving_distance',
                    'start_time', 'end_time', 'color',)
    list_select_related = ('optimisation', 'driver',)


@admin.register(RoutePoint)
class RoutePointAdmin(admin.ModelAdmin):
    list_display = ('point_object', 'point_kind', 'point_content_type', 'route', 'number', 'driving_time', 'distance',
                    'start_time', 'end_time', 'utilized_capacity', 'service_time')
    list_select_related = ('route',)

    def get_queryset(self, request):
        return super(RoutePointAdmin, self).get_queryset(request).prefetch_related('point_object')


@admin.register(DriverRouteLocation)
class DriverRouteLocationAdmin(Select2FiltersMixin, admin.ModelAdmin):
    list_display = ('id', 'location', 'address')


@admin.register(OptimisationTask)
class OptimisationTaskAdmin(Select2FiltersMixin, admin.ModelAdmin):
    list_display = ('optimisation', 'status', 'created', )
    list_select_related = ('optimisation', )


@admin.register(EngineRun)
class EngineRunAdmin(Select2FiltersMixin, admin.ModelAdmin):
    form = EngineRunForm
    list_display = ('optimisation', 'state', 'created', 'modified',)
    list_select_related = ('optimisation', 'engine_log')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
