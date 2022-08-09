from __future__ import absolute_import, unicode_literals

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin
from django.urls import reverse
from django.utils.html import format_html

from constance.admin import Config, ConstanceAdmin

from base.models import Car, CSVDriverSchedulesFile, DriverScheduleUpload, Invite, Member, SampleFile
from radaro_utils.radaro_admin.admin import RemoveDeleteActionMixin, Select2FiltersMixin, SuperuserRequiredMixin
from reporting.admin import TrackableModelAdmin

from .actions import activate_selected_members, deactivate_selected_members
from .filters import InitiatorOnlyListFilter, LastPingDateFilter
from .forms import InviteCreationForm, MemberChangeForm, MemberCreationForm
from .views import CMSWeeklyUsageReport, DriverScheduleImport, SMSTestView, get_group_manager_merchants

admin.site.register_view(r'test-sms/', name='Test SMS', view=SMSTestView.as_view(), visible=True)
admin.site.register_view(r'test-weekly-report/', name='Weekly Radaro usage report', view=CMSWeeklyUsageReport.as_view(),
                         visible=True)
admin.site.register_view(r'drivers-schedule-import/', name="Bulk upload of drivers' schedule and capacity",
                         view=DriverScheduleImport.as_view(), visible=True, urlname='drivers_schedule_import')

    
@admin.register(Member)
class MemberAdmin(SuperuserRequiredMixin, RemoveDeleteActionMixin, Select2FiltersMixin, TrackableModelAdmin, UserAdmin):
    excluded_fields_from_tracking = ('avatar',)

    add_form = MemberCreationForm
    form = MemberChangeForm
    change_form_template = 'admin/base/member/change_form.html'

    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email', 'avatar', 'phone', 'language', 'deleted',
                                      'deleted_at')}),
        ('Important dates', {'fields': ('last_login', 'date_joined', 'last_ping', 'has_internet_connection')}),
        ('Merchant info', {'fields': ('merchant', 'sub_branding', 'car', 'role', 'work_status', 'is_offline_forced',
                                      'skill_sets')}),
        ('Group Manager info', {'fields': ('merchants', 'sub_brandings', 'show_only_sub_branding_jobs')}),
        ('Order info', {'fields': ('starting_point', 'starting_hub', 'ending_point', 'ending_hub')}),
    )
    superuser_fieldsets = (
        ('Permissions', {'fields': ('is_active', 'is_confirmed', 'is_staff', 'is_superuser')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'email', 'phone', 'password1', 'password2'),
        }),
    )
    list_display = ('email', 'first_name', 'last_name', 'phone', 'last_ping', 'work_status', 'is_active',
                    'is_staff', 'member_id', 'merchant', 'merchant_position', 'view_orders', 'deleted')
    list_filter = ('role', 'merchant', 'sub_branding', 'work_status', 'is_active', LastPingDateFilter, 'deleted')
    search_fields = ('first_name', 'last_name', 'email', 'merchant__name', 'member_id', 'phone', 'username',)
    readonly_fields = ('last_login', 'date_joined', 'last_ping', 'has_internet_connection', 'is_offline_forced',
                       'deleted_at')
    ordering = ('-id',)
    actions = (deactivate_selected_members, activate_selected_members,)

    raw_id_fields = ('merchant', 'sub_branding', 'car', 'starting_point', 'starting_hub', 'ending_point', 'ending_hub')
    autocomplete_lookup_fields = {
        'fk': ['merchant', 'sub_branding', 'starting_point', 'starting_hub', 'ending_point', 'ending_hub']
    }

    def view_orders(self, member):
        if member.role == Member.NOT_DEFINED:
            return '-'
        elif member.role == Member.DRIVER:
            url_param_name = 'driver__id__exact'
        else:
            url_param_name = 'manager__id__exact'
        url = "%(url)s?%(url_param_name)s=%(id)s" % {
            'url': reverse('admin:tasks_order_changelist'),
            'url_param_name': url_param_name,
            'id': member.id
        }
        return format_html('<a href="%s">View orders</a>' % url)
    view_orders.short_description = 'View orders'

    def get_queryset(self, request):
        qs = self.model.all_objects.get_queryset()
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        return qs


class InlineUserAdmin(admin.TabularInline):
    model = get_user_model()
    fields = ('first_name', 'last_name', 'last_login',
              'email', 'phone', 'merchant_position',
              'date_joined')
    extra = 1
    max_num = 0

    def get_readonly_fields(self, request, obj=None):
        return 'last_login', 'date_joined', 'merchant_position'


@admin.register(Invite)
class InviteAdmin(Select2FiltersMixin, admin.ModelAdmin):
    model = Invite
    form = InviteCreationForm
    readonly_fields = ('invited', 'pin_code', 'pin_code_timestamp', 'token')
    list_select_related = ('merchant', )
    list_display = ('first_name', 'last_name', 'initiator', 'phone', 'email', 'position', 'get_merchant', )
    list_filter = (InitiatorOnlyListFilter, 'position', 'merchant')
    search_fields = ('first_name', 'last_name', 'email', 'phone', 'initiator__first_name', 'initiator__last_name',
                     'initiator__email', 'initiator__phone', 'invited__first_name', 'invited__last_name',
                     'invited__email', 'invited__phone', 'merchant__name', )

    raw_id_fields = ('initiator', )
    autocomplete_lookup_fields = {
        'fk': ['initiator', ]
    }

    def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
        if db_field.name == 'initiator':
            kwargs['queryset'] = Member.objects.filter(role__in=(Member.ADMIN, Member.MANAGER))
        return super(InviteAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def get_merchant(self, obj):
        return obj.merchant

    get_merchant.short_description = 'Merchant'
    get_merchant.admin_order_field = 'merchant__name'


@admin.register(SampleFile)
class SampleFileAdmin(admin.ModelAdmin):
    list_display = ('category', 'name_of_file', 'changed_at', 'uploaded_at')


@admin.register(Car)
class CarAdmin(Select2FiltersMixin, admin.ModelAdmin):
    list_display = ('id', 'car_type', 'capacity', 'driver_name', 'member_id', 'merchant')
    list_filter = ('car_type', 'member__merchant')
    list_select_related = ('member', 'member__merchant')
    search_fields = ('id', 'member__first_name', 'member__last_name', 'member__username', 'member__email',
                     'member__phone')

    def driver_name(self, car):
        return car.member.get_full_name()

    def member_id(self, car):
        return car.member.member_id

    def merchant(self, car):
        return car.member.merchant


class CSVDriversFileInline(admin.TabularInline):
    model = CSVDriverSchedulesFile
    extra = 0


@admin.register(DriverScheduleUpload)
class DriverScheduleUploadAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'created', 'method', 'status')
    inlines = (CSVDriversFileInline,)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('csv_file')


class ConfigAdmin(ConstanceAdmin):
    class Media:
        css = {
            'all': ('css/countries_custom_select.css',)
        }


try:
    admin.site.unregister([Config])
except admin.sites.NotRegistered:
    pass
finally:
    admin.site.register([Config], ConfigAdmin)

admin.site.register_view(r'group-manager/merchants/?$', urlname='cms-manager-merchants',
                         view=get_group_manager_merchants, visible=False)
