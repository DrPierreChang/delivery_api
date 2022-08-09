from __future__ import absolute_import

from urllib.parse import urlencode

from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.db.models import Prefetch
from django.urls import reverse
from django.utils.html import format_html

from push_notifications.admin import APNSDevice as externalAPNSDevice
from push_notifications.admin import GCMDevice as externalGCMDevice
from push_notifications.admin import WNSDevice as externalWNSDevice

from notification.admin.forms import DeviceForm, NotificationForm
from notification.models import (
    APNSDevice,
    Device,
    GCMDevice,
    MerchantMessageTemplate,
    Notification,
    PushNotificationsSettings,
    TemplateEmailAttachment,
    TemplateSMSMessage,
)
from notification.models.notifications import TemplateEmailMessage
from radaro_utils.filters.date_filters import DateTimeDescFilter, RadaroDateTimeRangeFilter
from radaro_utils.radaro_admin.admin import Select2FiltersMixin
from radaro_utils.radaro_admin.utils import build_field_attrgetter

from .views import CSVDeviceVersionReportView, DeviceVersionReportView

admin.site.register_view(r'device-versions/', name='Device versions report',
                         view=DeviceVersionReportView.as_view(), visible=True)
admin.site.register_view(r'device-versions/csv/', urlname='cms-device-versions-csv',
                         view=CSVDeviceVersionReportView.as_view(), visible=False)


class InactivityFilter(DateTimeDescFilter):
    title = 'Inactivity term'
    parameter_name = 'date_updated__lte'
    filtering_lookup = 'date_updated__lte'
    alias_for_lookup = 'Inactive'


class LastActivityDateFilter(DateTimeDescFilter):
    title = 'Activity term'
    parameter_name = 'date_updated__gte'
    filtering_lookup = 'date_updated__gte'
    alias_for_lookup = 'Active'


class LastPingDateFilter(DateTimeDescFilter):
    title = 'Last ping term'
    parameter_name = 'user__last_ping'
    filtering_lookup = 'user__last_ping__gte'
    alias_for_lookup = 'Last ping'


class DeviceHasUserFilter(SimpleListFilter):
    title = 'Is the device connected to the user?'
    parameter_name = 'user__isnull'

    def lookups(self, request, model_admin):
        return (
            (False, 'Yes'),
            (True, 'No')
        )

    def queryset(self, request, queryset):
        if self.value() in ['True', 'False']:
            return queryset.filter(**{self.parameter_name: self.value() == 'True'})


class DeviceAdmin(Select2FiltersMixin, admin.ModelAdmin):
    form = DeviceForm

    default_list_display = ('get_last_ping', 'user_link', 'get_merchant', 'app_name', 'app_version', 'device_name',
                            'os_version',)
    list_display = ('real_type', 'date_updated', 'in_use') + default_list_display
    list_filter = (InactivityFilter, LastActivityDateFilter, LastPingDateFilter, 'user__merchant', 'app_name',
                   'app_version', 'device_name', 'os_version', DeviceHasUserFilter, 'in_use')
    search_fields = ('user__first_name', 'user__last_name', 'os_version', 'device_name',)
    list_select_related = ('user__merchant', 'real_type', )

    raw_id_fields = ('user', )
    autocomplete_lookup_fields = {
        'fk': ['user', ],
    }

    def user_link(self, obj):
        if obj.user:
            return format_html('<a href="%s">%s</a>' % (reverse('admin:base_member_change', args=[obj.user.id]), obj.user))
        else:
            return '-'
    user_link.short_description = 'User'

    get_last_ping = build_field_attrgetter(
        'user.last_ping', short_description='Last ping', admin_order_field='user__last_ping')
    get_merchant = build_field_attrgetter(
        'user.current_merchant', short_description='Merchant', admin_order_field='user__merchant__name')


class APNSDeviceAdmin(DeviceAdmin):
    list_display = ('device_id', 'date_updated',) + DeviceAdmin.default_list_display


class GCMDeviceAdmin(DeviceAdmin):
    list_display = ('device_id', 'date_updated', ) + DeviceAdmin.default_list_display


class NotificationAdmin(Select2FiltersMixin, admin.ModelAdmin):
    form = NotificationForm
    list_display = ('__str__', )
    list_filter = ('devices__user', 'devices__user__merchant',)
    search_fields = ('message', )

    def get_queryset(self, request):
        prefetch = Prefetch('devices', queryset=Device.objects.select_related('user'))
        return super(NotificationAdmin, self).get_queryset(request).prefetch_related(prefetch)


class IsSentFilter(SimpleListFilter):
    title = 'Is sent'
    parameter_name = 'is_sent'

    def lookups(self, request, model_admin):
        return [(True, 'Yes'), (False, 'No')]

    def queryset(self, request, queryset):
        if self.value() is None:
            return queryset.all()

        if self.value() == 'True':
            return queryset.filter(sent_at__isnull=False)
        return queryset.filter(sent_at__isnull=True)


class MerchantMessageTemplateAdmin(admin.ModelAdmin):
    list_display = ('id', 'text', 'merchant', 'enabled',)
    list_filter = ('template_type', 'merchant', 'enabled',)
    fields = ('text', 'html_text', 'subject', 'merchant', 'template_type', 'enabled')

    raw_id_fields = ('merchant', )
    autocomplete_lookup_fields = {
        'fk': ['merchant', ],
    }

    def get_queryset(self, request):
        qs = super(MerchantMessageTemplateAdmin, self).get_queryset(request)
        return qs.select_related('merchant')


class BaseTemplateMessageAdmin(admin.ModelAdmin):
    list_display = ('text', 'sent_at', 'template_id')
    list_select_related = ('template', 'template__merchant')
    list_filter = (
        'template__template_type', 'template__merchant', IsSentFilter, ('sent_at', RadaroDateTimeRangeFilter),
    )

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return [field.name for field in obj.__class__._meta.fields]
        return super(BaseTemplateMessageAdmin, self).get_readonly_fields(request, obj)

    def get_template_type(self, obj):
        return obj.template.get_template_type_display()

    def get_merchant(self, obj):
        return obj.template.merchant

    get_template_type.short_description = 'Type'
    get_template_type.admin_order_field = 'template__template_type'

    get_merchant.short_description = 'Merchant'
    get_merchant.admin_order_field = 'template__merchant'


class TemplateSMSMessageAdmin(BaseTemplateMessageAdmin):
    list_display = ('phone', 'sender', 'text', 'get_template_type', 'segment_count',
                    'sent_at', 'price', 'template_id', 'get_merchant')
    search_fields = ('phone', 'text',)


class TemplateEmailAttachmentInline(admin.TabularInline):
    model = TemplateEmailAttachment
    extra = 0


class TemplateEmailMessageAdmin(BaseTemplateMessageAdmin):
    list_display = ('email', 'get_template_type', 'sent_at', 'message_id', 'template_id',
                    'get_user', 'get_merchant', )
    inlines = [TemplateEmailAttachmentInline, ]

    def get_user(self, obj):
        query = urlencode({'email': obj.email})
        return format_html('<a href="%s?%s">%s</a>' % \
                   (reverse('admin:base_member_changelist'), query, 'User'))
    get_user.short_description = 'User'


admin.site.register(Notification, NotificationAdmin)
admin.site.register(Device, DeviceAdmin)
admin.site.register(GCMDevice, GCMDeviceAdmin)
admin.site.register(APNSDevice, APNSDeviceAdmin)
admin.site.unregister([externalAPNSDevice, externalGCMDevice, externalWNSDevice])
admin.site.register(PushNotificationsSettings)
admin.site.register(MerchantMessageTemplate, MerchantMessageTemplateAdmin)
admin.site.register(TemplateSMSMessage, TemplateSMSMessageAdmin)
admin.site.register(TemplateEmailMessage, TemplateEmailMessageAdmin)
