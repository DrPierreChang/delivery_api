from __future__ import absolute_import

from django.contrib import admin
from django.db import models
from django.db.models.fields import AutoField
from django.forms import model_to_dict
from django.http import Http404, HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html

from constance import config
from pinax.stripe.admin import customer_search_fields
from pinax.stripe.models import Charge

from base.admin import InlineUserAdmin
from documents.models import Tag
from merchant.admin.utils import (
    copy_merchant_logo,
    deactivate_way_back,
    on_change_merchant_type,
    reset_autogenerated_settings,
)
from merchant.models import DriverHub, Hub, HubLocation, Label, Merchant, MerchantGroup, SkillSet, SubBranding
from merchant_extension.models import EndOfDayChecklist, JobChecklist, StartOfDayChecklist
from notification.admin.inlines import MerchantTemplateInlineAdmin
from radaro_utils.countries import countries as country_list
from radaro_utils.radaro_admin.admin import RemoveDeleteActionMixin, Select2FiltersMixin
from reporting.admin import TrackableModelAdmin
from tasks.admin import InlineTerminationCodeAdmin

from .forms import DriverHubForm, MerchantForm, MerchantGroupForm, SubBrandingForm
from .views import CMSMerchantReportsView, GenerateCSVReportView, get_drivers_and_hubs

admin.site.unregister([Charge])
admin.site.register_view(r'report/', name='Merchant usage report', view=CMSMerchantReportsView.as_view(), visible=True)
admin.site.register_view(r'report/generate/', urlname='cms-report-generate',
                         view=GenerateCSVReportView.as_view(), visible=False)
admin.site.register_view(r'driverhubs/?$', urlname='cms-driverhubs', view=get_drivers_and_hubs, visible=False)


class TagInline(admin.TabularInline):
    model = Tag
    extra = 0


class MerchantCountryFilter(admin.SimpleListFilter):
    title = 'Country'
    parameter_name = 'countries'

    def lookups(self, request, model_admin):
        allowed_countries = config.ALLOWED_COUNTRIES
        return [(code, country) for code, country in country_list if code in allowed_countries]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(countries__contains=[self.value()])


class BaseChecklistFilter(admin.SimpleListFilter):
    filtering_lookup = None
    checklist_model = None

    def lookups(self, request, model_admin):
        checklists = self.checklist_model.objects.all()
        return ((checklist.id, checklist.title) for checklist in checklists)

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(**{self.filtering_lookup: self.value()})


class StartOfDayChecklistFilter(BaseChecklistFilter):
    title = 'Start-of-Day Checklist'
    parameter_name = 'sod_checklist__id'
    filtering_lookup = 'sod_checklist__id'
    checklist_model = StartOfDayChecklist


class EndOfDayChecklistFilter(BaseChecklistFilter):
    title = 'End-of-Day Checklist'
    parameter_name = 'eod_checklist__id'
    filtering_lookup = 'eod_checklist__id'
    checklist_model = EndOfDayChecklist


class ChecklistFilter(BaseChecklistFilter):
    title = 'Checklist'
    parameter_name = 'checklist__id'
    filtering_lookup = 'checklist__id'
    checklist_model = JobChecklist


@admin.register(Merchant)
class MerchantAdmin(RemoveDeleteActionMixin, TrackableModelAdmin):
    model = Merchant

    form = MerchantForm
    change_form_template = 'admin/merchant/merchant_model/change_form.html'

    inlines = (MerchantTemplateInlineAdmin, InlineUserAdmin, InlineTerminationCodeAdmin, TagInline)

    _fields = [f.name for f in model._meta.get_fields() if not isinstance(f, AutoField) and f.editable]
    _include = ('created_at',)
    _exclude = ('api_server_url',)

    _screen_text_field_section = (
        'job_failure_screen_text', 'assigned_job_screen_text',
        'not_assigned_job_screen_text', 'pickup_failure_screen_text', 'help_for_screen_text',
        'time_today_reminder',
    )
    _reports_field_section = (
        'merchant_group', 'reports_frequency', 'jobs_export_email',
        'survey_reports_frequency', 'survey_export_email',
    )

    _general_field_section = tuple(
        [field for field in _fields if field not in (
            'job_failure_screen_text', 'assigned_job_screen_text', 'not_assigned_job_screen_text',
            'help_for_screen_text', 'merchant_group', 'reports_frequency', 'jobs_export_email',
            'survey_reports_frequency', 'survey_export_email', 'api_server_url',
            'pickup_failure_screen_text', 'time_today_reminder'
        )]
    ) + _include

    fieldsets = (
        (None, {'fields': _general_field_section}),
        (None, {'fields': _reports_field_section}),
        (None, {'fields': _screen_text_field_section}),
    )

    list_display = (
        'name', 'created_at', 'balance', 'phone', 'address', 'allow_geofence', 'enable_delivery_confirmation',
        'store_url', 'is_blocked', 'countries', 'sms_enable', 'show_orders', 'show_members'
    )
    search_fields = ('name', 'address', 'store_url', 'phone')
    list_filter = (
        'is_blocked', 'enable_delivery_confirmation', 'enable_delivery_pre_confirmation', MerchantCountryFilter,
        'geofence_settings', 'merchant_group', 'enable_labels', 'use_way_back_status', 'use_hubs', 'path_processing',
        'advanced_completion', 'high_resolution', 'driver_can_create_job', 'in_app_jobs_assignment',
        'route_optimization',
        StartOfDayChecklistFilter, EndOfDayChecklistFilter, ChecklistFilter
    )
    readonly_fields = ('webhook_verification_token', 'created_at', 'merchant_identifier', 'help_for_screen_text',
                       'api_multi_key')

    def get_queryset(self, request):
        qs = super(MerchantAdmin, self).get_queryset(request)
        return qs.annotate(members_count=models.Count('member'))

    def save_model(self, request, obj, form, change):
        try:
            old_obj = Merchant.objects.get(id=obj.id)
        except Merchant.DoesNotExist:
            old_obj = None
        if old_obj and old_obj.use_way_back_status and not obj.use_way_back_status:
            deactivate_way_back(obj, request.user)
        result = super(MerchantAdmin, self).save_model(request, obj, form, change)

        if not old_obj and 'clone' in request.GET:
            source_obj_id = request.GET.get('clone')
            reset_autogenerated_settings(obj.id, source_obj_id)
            if form.cleaned_data['logo'] is None:
                copy_merchant_logo(obj.id, source_obj_id)

        if not old_obj or old_obj.merchant_type != obj.merchant_type:
            on_change_merchant_type(obj)
        return result

    def show_orders(self, obj):
        return format_html('<a href="%s?merchant__id__exact=%s">%s</a>' % \
               (reverse('admin:tasks_order_changelist'), obj.id, 'Show orders'))
    show_orders.short_description = 'Show orders'

    def show_members(self, obj):
        return format_html('<a href="%s?merchant__id__exact=%s">%s</a>' % \
               (reverse('admin:base_member_changelist'), obj.id, 'View members (%s)' % obj.members_count))
    show_members.short_description = 'View members'

    def help_for_screen_text(self, obj):
        from merchant.renderers import ScreenTextRenderer
        return ScreenTextRenderer.get_help_for_screen_text()
    help_for_screen_text.short_description = 'Variables for Customer tracking page:'

    def get_changeform_initial_data(self, request):
        if 'clone' in request.GET:
            try:
                obj = Merchant.objects.get(pk=request.GET.get('clone'))
                initial_data = model_to_dict(obj)
                initial_data['name'] = obj.name + '-copy'
            except (ValueError, Merchant.DoesNotExist):
                raise Http404
            return initial_data
        return super().get_changeform_initial_data(request)

    def response_change(self, request, obj):
        if "_clone-merchant" in request.POST:
            return HttpResponseRedirect('{}{}'.format(reverse('admin:merchant_merchant_add'),
                                                      '?clone={}'.format(obj.pk)))
        return super().response_change(request, obj)


@admin.register(SubBranding)
class SubBrandingMerchant(Select2FiltersMixin, TrackableModelAdmin):
    form = SubBrandingForm

    list_display = ('name', 'id', 'sms_sender', 'merchant', 'phone', 'store_url')
    search_fields = ('name', 'store_url', 'id')
    list_filter = ('merchant', )

    raw_id_fields = ('merchant', )
    autocomplete_lookup_fields = {
        'fk': ['merchant', ],
    }


@admin.register(MerchantGroup)
class MerchantGroupAdmin(admin.ModelAdmin):
    form = MerchantGroupForm

    list_display = ('title', 'show_merchants')
    search_fields = ('title', 'merchants__name')

    def show_merchants(self, obj):
        return format_html('<a href="%s?merchant_group__id__exact=%s">%s</a>' % \
               (reverse('admin:merchant_merchant_changelist'), obj.id, 'Merchants list'))
    show_merchants.short_description = 'Merchants list'

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            obj.delete()


@admin.register(HubLocation)
class HubLocationAdmin(admin.ModelAdmin):
    list_display = ('address', 'location', 'created_at', )

    readonly_fields = ('created_at', )


@admin.register(Hub)
class HubAdmin(TrackableModelAdmin):
    list_display = ('name', 'phone', 'location', 'merchant', )
    list_filter = ('merchant', )
    list_select_related = ('merchant', )

    search_fields = ('name', 'phone', 'merchant__name', )

    raw_id_fields = ('location', 'merchant', )
    autocomplete_lookup_fields = {
        'fk': ['location', 'merchant', ],
    }


@admin.register(Label)
class LabelAdmin(TrackableModelAdmin):
    list_filter = ('merchant', )
    list_display = ('name', 'id', 'merchant', 'color')

    list_select_related = ('merchant', )

    search_fields = ('id', 'name', )

    raw_id_fields = ('merchant', )
    autocomplete_lookup_fields = {
        'fk': ['merchant', ],
    }


@admin.register(SkillSet)
class SkillSetAdmin(TrackableModelAdmin):
    list_filter = ('merchant', )
    list_display = ('name', 'id', 'merchant', 'color')

    list_select_related = ('merchant',)


@admin.register(Charge)
class ChargeAdmin(admin.ModelAdmin):
    list_display = ["stripe_id", "customer", "view_customer_merchant", "amount",
                    "description", "paid", "disputed",
                    "refunded", "receipt_sent", "created_at"]
    search_fields = ["stripe_id", "customer__stripe_id", "invoice__stripe_id"] + customer_search_fields()
    list_filter = ["paid", "disputed", "refunded", "customer__user__merchant", "description"]
    list_select_related = ["customer", "customer__user", "customer__user__merchant"]
    raw_id_fields = ["customer", "invoice"]

    def view_customer_merchant(self, obj):
        return obj.customer.user.current_merchant

    view_customer_merchant.short_description = 'Merchant'


@admin.register(DriverHub)
class DriverHubAdmin(admin.ModelAdmin):
    form = DriverHubForm
    list_filter = ('hub', 'driver')
    list_select_related = ('hub', 'driver')