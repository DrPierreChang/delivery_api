from __future__ import absolute_import

from django import forms
from django.conf import settings
from django.conf.urls import url
from django.contrib import admin, messages
from django.db.models import CharField, Prefetch, Q, Sum, Value
from django.http import JsonResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.http import urlencode
from django.utils.safestring import mark_safe

from django_markdown.widgets import AdminMarkdownWidget

from base.models import Member
from documents.models import OrderConfirmationDocument
from driver.filters import DriverOnlyListFilter
from integrations.models import RevelSystem
from merchant.models import Label, SkillSet, SubBranding
from radaro_utils.filters.date_filters import RadaroDateTimeRangeFilter
from radaro_utils.radaro_admin.admin import MaxNumInlinesMixin, RemoveDeleteActionMixin, Select2FiltersMixin
from radaro_utils.radaro_admin.utils import build_field_attrgetter
from radaro_utils.radaro_admin.widgets import MerchantRawIdWidget
from radaro_utils.signals import post_admin_page_action
from reporting.admin import TrackableModelAdmin
from reporting.context_managers import track_fields_on_change
from tasks.mixins.order_status import OrderStatus
from tasks.models import (
    SKID,
    Barcode,
    BulkDelayedUpload,
    ConcatenatedOrder,
    Customer,
    Order,
    OrderConfirmationPhoto,
    OrderLocation,
    Pickup,
)
from tasks.models.bulk import CSVOrdersFile, OrderPrototype
from tasks.models.external import ExternalJob
from tasks.models.orders import OrderPickUpConfirmationPhoto, OrderPreConfirmationPhoto, OrderPrice, generate_id
from tasks.models.terminate_code import SUCCESS_CODES_DISABLED_MSG, TerminateCode
from tasks.utils import image_file, related_images_gallery
from webhooks.filters import ExternalOrderMerchantAPIKeyFilter, OrderMerchantAPIKeyFilter
from webhooks.models import MerchantAPIKey

from ..signal_receivers.concatenated_order import co_auto_processing
from .filters import ExternalJobFilter


class OrderForm(forms.ModelForm):
    comment = forms.CharField(widget=forms.Textarea(), required=False)
    description = forms.CharField(widget=AdminMarkdownWidget(), required=False)
    confirmation_comment = forms.CharField(widget=forms.Textarea(), required=False)
    customer_comment = forms.CharField(widget=forms.Textarea(), required=False)

    class Meta:
        model = Order
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        self.obj = kwargs.pop('obj', None)
        # map_ = Order.get_current_available_statuses(self.obj.status)
        # choices = (st for st in Order._status if st[0] in map_ + [self.obj.status])
        choices = Order._status
        super(OrderForm, self).__init__(*args, **kwargs)
        self.fields['status'] = forms.ChoiceField(choices=choices)
        if hasattr(self.instance, 'merchant'):
            merchant_id = self.instance.merchant_id
            self.fields['terminate_codes'].queryset = TerminateCode.objects.filter(merchant_id=merchant_id)
            self.fields['labels'].queryset = Label.objects.filter(merchant_id=merchant_id)
            self.fields['sub_branding'].queryset = SubBranding.objects.filter(merchant_id=merchant_id)
            self.fields['skill_sets'].queryset = SkillSet.objects.filter(merchant_id=merchant_id)

            # modification of raw_id_fields fields
            raw_id_fields = ('customer', 'driver',  'wayback_hub', 'pickup', 'concatenated_order')
            for field in raw_id_fields:
                self.fields[field].widget = MerchantRawIdWidget(
                    rel=self.instance._meta.get_field(field).remote_field,
                    admin_site=admin.site,
                    attrs={'object': self.instance}
                )

    def clean(self):
        cleaned_data = super().clean()
        if all([cleaned_data['deleted'], not (len(self.changed_data) == 1 and 'deleted' in self.changed_data)]):
            raise forms.ValidationError('You can\'t edit job marked as deleted')
        return cleaned_data


class OrderConfirmationPhotoInline(MaxNumInlinesMixin, admin.TabularInline):
    model = OrderConfirmationPhoto
    extra = 0
    readonly_fields = ('image_tag', )
    image_tag = image_file('image', 'Confirmation photo', height=250)


class OrderConfirmationDocumentInline(MaxNumInlinesMixin, admin.TabularInline):
    model = OrderConfirmationDocument
    extra = 0


class OrderPickUpConfirmationPhotoInline(MaxNumInlinesMixin, admin.TabularInline):
    model = OrderPickUpConfirmationPhoto
    extra = 0
    readonly_fields = ('image_tag', )
    verbose_name = 'order pick up confirmation photo'
    verbose_name_plural = 'order pick up confirmation photos'
    image_tag = image_file('image', 'Pick up confirmation photo', height=250)


@admin.register(ExternalJob)
class ExternalJobAdmin(admin.ModelAdmin):
    list_display = ('external_id', 'source', 'order')
    search_fields = ('external_id',)
    list_filter = (ExternalOrderMerchantAPIKeyFilter,)
    list_select_related = ('order',)

    def get_queryset(self, request):
        return super(ExternalJobAdmin, self).get_queryset(request).select_related('order')

    def get_order(self, obj):
        if hasattr(obj, 'order'):
            return format_html(
                '<a href="%s">%s</a>' % (reverse('admin:tasks_order_change', args=[obj.order.id]), 'Order')
            )
        else:
            return '-'
    get_order.short_description = 'Order'


class OrderPreInspectionPhotoInline(MaxNumInlinesMixin, admin.TabularInline):
    model = OrderPreConfirmationPhoto
    extra = 0
    readonly_fields = ('image_tag', )
    verbose_name = 'order pre-inspection photo'
    verbose_name_plural = 'order pre-inspection photos'
    image_tag = image_file('image', 'Pre-inspection photo', height=250)


class OrderSkidsInline(admin.TabularInline):
    model = SKID
    extra = 0
    verbose_name = 'SKID adjustment'
    verbose_name_plural = 'SKID adjustment'


@admin.register(OrderPrice)
class OrderPriceAdmin(RemoveDeleteActionMixin, Select2FiltersMixin, admin.ModelAdmin):
    list_display = ('title', 'order_id', 'merchant', 'driver', 'status', 'job_price', 'locations_price',
                    'total_sms_price', 'total_cost')
    fields = ('title', 'locations_cost', 'total_sms_price', 'total_cost', 'order_id', 'driver')
    readonly_fields = ('title', 'locations_cost', 'total_sms_price', 'total_cost', 'order_id', 'driver')

    search_fields = ('title', 'order_id', 'deleted', 'external_job__external_id', 'customer__name', 'id')
    list_filter = (
        'status',
        'merchant',
        DriverOnlyListFilter,
        ExternalJobFilter,
        OrderMerchantAPIKeyFilter,
    )

    fields_for_calculation = ('job_price', 'locations_price', 'total_sms_price', 'total_cost')
    change_list_template = 'admin/tasks/orderprice/change_list.html'
    list_per_page = 25

    def get_urls(self):
        urls = super(OrderPriceAdmin, self).get_urls()
        custom_urls = [url(r'^calculate/(?P<order_id>[0-9]+)$', self.calculated_price_view, name='calculate price'),]
        return custom_urls + urls

    def get_queryset(self, request):
        qs = super(OrderPriceAdmin, self).get_queryset(request).select_related('merchant', 'driver')
        qs = qs.annotate(**{key: Value('...', output_field=CharField()) for key in self.fields_for_calculation})
        return qs

    def get_object(self, request, object_id, from_field=None):
        obj = super(OrderPriceAdmin, self).get_object(request, object_id, from_field)
        if obj:
            data = self._calculate_price(obj)
            for k, v in data.items():
                setattr(obj, k, v)
        return obj

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def job_price(self, obj):
        return obj.job_price
    job_price.short_description = 'Job price'

    def total_sms_price(self, obj):
        return obj.total_sms_price
    total_sms_price.short_description = 'Total SMS price'

    def locations_price(self, obj):
        return obj.locations_price
    locations_price.short_description = 'Locations price'

    def total_cost(self, obj):
        return obj.total_cost
    total_cost.short_description = 'Total job price'

    def _calculate_price(self, obj):
        data = {
            'job_price': float(obj.cost or 0),
            'locations_price': float(obj.locations_cost or 0),
            'total_sms_price': obj.templatesmsmessage_set.all().aggregate(Sum('price'))['price__sum'] or 0.0
        }
        data['total_cost'] = data['job_price'] + data['locations_price'] + data['total_sms_price']
        return data

    def calculated_price_view(self, request, order_id):
        user = request.user
        can_show = user.is_authenticated and (user.is_staff or user.is_superuser)
        op = Order.objects.filter(order_id=order_id).first()
        data = self._calculate_price(op) if can_show and op else {}
        return JsonResponse(data)


class BarcodeInlineAdmin(admin.TabularInline):
    model = Barcode
    extra = 0
    fields = ('code_data', 'required', 'scanned_at_the_warehouse', 'scanned_upon_delivery')


@admin.register(Order)
class OrderAdmin(RemoveDeleteActionMixin, Select2FiltersMixin, TrackableModelAdmin):
    excluded_fields_from_tracking = ('confirmation_signature', 'labels', 'pre_confirmation_signature',
                                     'pick_up_confirmation_signature')

    form = OrderForm
    inlines = [
        BarcodeInlineAdmin,
        OrderConfirmationPhotoInline,
        OrderPreInspectionPhotoInline,
        OrderPickUpConfirmationPhotoInline,
        OrderConfirmationDocumentInline,
        OrderSkidsInline,
    ]
    change_form_template = 'admin/tasks/order/change_form.html'

    raw_id_fields = ('pickup_address', 'deliver_address', 'starting_point', 'customer', 'external_job', 'driver',
                     'manager', 'merchant', 'ending_point', 'bulk', 'driver_checklist', 'model_prototype',
                     'wayback_point', 'wayback_hub', 'pickup', 'concatenated_order')
    autocomplete_lookup_fields = {
        'fk': ['pickup_address', 'deliver_address', 'starting_point', 'customer', 'driver', 'manager', 'merchant',
               'ending_point', 'wayback_point', 'wayback_hub', 'pickup'],
    }
    list_select_related = ('merchant', 'manager', 'driver', 'manager__merchant', 'driver__merchant', 'customer',
                           'external_job', 'actual_device', 'sub_branding', 'pickup')
    exclude = ('path', 'wayback_distance', 'confirmation_photos_tag', 'pre_confirmation_photos_tag', 'actual_device',)
    readonly_fields = ('order_id', 'order_token', 'confirmation_photos_tag', 'time_inside_geofence', 'time_at_job',
                       'confirmation_signature_tag', 'updated_at', 'created_from_external_api',
                       'pre_confirmation_photos_tag', 'pre_confirmation_signature_tag',
                       'pick_up_confirmation_photos_tag', 'pick_up_confirmation_signature_tag',
                       'get_app_version', 'get_os_version', 'get_device_name', 'is_concatenated_order')
    search_fields = ('title', 'order_id', 'deleted', 'external_job__external_id', 'customer__name', 'customer__phone',)
    list_filter = (
        DriverOnlyListFilter,
        # ManagerOnlyListFilter,
        'status',
        'merchant',
        'sub_branding',
        ('created_at', RadaroDateTimeRangeFilter),
        ExternalJobFilter,
        OrderMerchantAPIKeyFilter,
        'deleted',
        'changed_in_offline',
    )
    list_display = ('title', 'created_from_external_api', 'merchant', 'sub_branding', 'deleted', 'status', 'created_at',
                    'manager', 'driver', 'customer', 'get_customer_phone', 'deliver_before',
                    'list_display_confirmation_signature_tag', 'confirmation_photos_tag',
                    'list_display_pre_confirmation_signature_tag', 'pre_confirmation_photos_tag',
                    'list_display_pick_up_confirmation_signature_tag', 'pick_up_confirmation_photos_tag',
                    'order_id', 'deadline_notified', 'show_driver_path', 'changed_in_offline', 'show_job_report',
                    'get_app_version', 'get_os_version', 'get_device_name', )

    confirmation_signature_tag = image_file('confirmation_signature', 'Confirmation signature', height=250)
    pre_confirmation_signature_tag = image_file('pre_confirmation_signature', 'Pre-inspection signature', height=250)
    pick_up_confirmation_signature_tag = image_file('pick_up_confirmation_signature', 'Pick up confirmation signature',
                                                    height=250)
    list_display_confirmation_signature_tag = image_file('confirmation_signature', 'Confirmation signature',
                                                         width=100, height=100)
    list_display_pre_confirmation_signature_tag = image_file('pre_confirmation_signature', 'Pre-inspection signature',
                                                             width=100, height=100)
    list_display_pick_up_confirmation_signature_tag = image_file('pick_up_confirmation_signature',
                                                                 'Pick up confirmation signature',
                                                                 width=100, height=100)

    confirmation_photos_tag = related_images_gallery('order_confirmation_photos', 'image', 'Confirmation photos')
    pre_confirmation_photos_tag = related_images_gallery('pre_confirmation_photos', 'image',
                                                         'Pre-inspection photos')
    pick_up_confirmation_photos_tag = related_images_gallery('pick_up_confirmation_photos', 'image',
                                                             'Pick up confirmation photos')

    def make_unassigned(self, request, queryset):
        qs = queryset.filter(status=Order.ASSIGNED)
        post_admin_page_action.send(Order, ids=list(qs.values_list('id', flat=True)), action_type='unassign')
        rows_updated = qs.update(status=Order.NOT_ASSIGNED, driver=None)
        if rows_updated == 1:
            message_bit = "1 order was"
        else:
            message_bit = "%s orders were" % rows_updated
        self.message_user(request, "%s successfully marked as unassigned." % message_bit)
    make_unassigned.short_description = "Mark selected orders as unassigned"

    def make_deleted(self, request, queryset):
        post_admin_page_action.send(Order, ids=list(queryset.values_list('id', flat=True)), action_type='delete')

        rows_updated = 0
        for order in queryset:
            order.safe_delete()
            rows_updated += 1

        if rows_updated == 1:
            message_bit = "1 order was"
        else:
            message_bit = "%s orders were" % rows_updated
        self.message_user(request, "%s successfully marked as deleted." % message_bit)
    make_deleted.short_description = "Mark selected orders as deleted"

    def show_driver_path(self, obj):
        if obj.status in OrderStatus.status_groups.FINISHED and obj.serialized_track:
            digest = obj.merchant_daily_hash()
            url_string = settings.FRONTEND_URL + '/replay/%s?hash=%s&domain=%s' \
                                                 % (obj.order_token, digest, settings.CURRENT_HOST)
            return format_html("<a target='_blank' href='{url}'>{name}</a>", url=url_string, name='Replay route')
        else:
            return None
    show_driver_path.short_description = 'Driver\'s movement'

    def show_job_report(self, obj):
        return format_html("<a target='_blank' href='{url}'>{name}</a>", url=obj.full_report_link, name='Job report')
    show_job_report.short_description = 'Job report'

    get_customer_phone = build_field_attrgetter('customer.phone', short_description='Customer Phone')
    get_app_version = build_field_attrgetter('actual_device.app_version', short_description='App Version')
    get_os_version = build_field_attrgetter('actual_device.os_version', short_description='OS Version')
    get_device_name = build_field_attrgetter('actual_device.device_name', short_description='Device Name')

    actions = [make_unassigned, make_deleted]

    class Media:
        js = (
            'js/admin_filters_select2/jquery.init.js',
            'https://cdnjs.cloudflare.com/ajax/libs/select2/4.0.3/js/select2.min.js',
            'js/admin_filters_select2/admin_filters_select2.js',
            'js/lightbox2/js/lightbox.min.js',
        )
        css = {
            'all': ('js/lightbox2/css/lightbox.css',
                    'https://cdnjs.cloudflare.com/ajax/libs/select2/4.0.3/css/select2.min.css')
        }

    def get_changeform_initial_data(self, request):
        initial = super(OrderAdmin, self).get_changeform_initial_data(request)
        initial['order_id'] = generate_id(length=7, cmpr=Order.order_id_comparator, prefix=1)
        return initial

    def get_form(self, request, obj=None, **kwargs):
        OrderFormClass = super(OrderAdmin, self).get_form(request, obj, **kwargs)

        class OrderFormWithRequest(OrderFormClass):
            def __new__(cls, *args, **kwargs):
                kwargs['request'] = request
                kwargs['obj'] = obj
                return OrderFormClass(*args, **kwargs)

        return OrderFormWithRequest

    def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
        if db_field.name == 'driver':
            kwargs['queryset'] = Member.objects.filter(role__in=[Member.DRIVER, Member.MANAGER_OR_DRIVER])
        return super(OrderAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

    def get_queryset(self, request):
        return Order.all_objects.all().select_related(*self.list_select_related)\
            .prefetch_related(Prefetch('order_confirmation_photos',
                                       queryset=OrderConfirmationPhoto.objects.filter(image__isnull=False)),
                              Prefetch('pre_confirmation_photos',
                                       queryset=OrderPreConfirmationPhoto.objects.filter(image__isnull=False)),
                              Prefetch('pick_up_confirmation_photos',
                                       queryset=OrderPickUpConfirmationPhoto.objects.filter(image__isnull=False))
                              )


@admin.register(Customer)
class CustomerAdmin(Select2FiltersMixin, admin.ModelAdmin):
    list_filter = ('merchant',)
    list_display = ('name', 'email', 'phone', 'merchant')
    list_select_related = ('merchant', )
    search_fields = ('name', 'email')

    raw_id_fields = ('last_address', 'merchant',)
    autocomplete_lookup_fields = {
        'fk': ['last_address', 'merchant', ],
    }


@admin.register(Pickup)
class PickupAdmin(Select2FiltersMixin, admin.ModelAdmin):
    list_filter = ('merchant',)
    list_display = ('name', 'email', 'phone', 'merchant')
    list_select_related = ('merchant', )
    search_fields = ('name', 'email')

    raw_id_fields = ('merchant',)
    autocomplete_lookup_fields = {
        'fk': ['merchant', ],
    }


class OrderPrototypeForm(forms.ModelForm):
    class Meta:
        model = OrderPrototype
        # exclude = ('external_job',)
        fields = '__all__'


class OrderPrototypeInlineAdmin(admin.TabularInline):
    model = OrderPrototype
    extra = 0
    form = OrderPrototypeForm
    raw_id_fields = ('external_job', 'bulk')


class CSVOrdersFileAdmin(admin.TabularInline):
    model = CSVOrdersFile
    extra = 0


class OrderPrototypeAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'processed', 'bulk', 'ready', 'line', 'external_job')
    list_filter = ('bulk', 'processed',)
    list_select_related = ('external_job', 'bulk')
    raw_id_fields = list_select_related
    form = OrderPrototypeForm

    def __init__(self, model, admin_site):
        self.external_sources = {
            MerchantAPIKey: lambda x: Q(creator__merchant_id=x.merchant_id),
            RevelSystem: lambda x: Q(merchant_id=x.merchant_id),
        }
        super(OrderPrototypeAdmin, self).__init__(model, admin_site)

    def get_form(self, request, obj=None, **kwargs):
        form = super(OrderPrototypeAdmin, self).get_form(request, obj, **kwargs)
        form.base_fields['bulk'].queryset = BulkDelayedUpload.objects.filter(merchant=obj.bulk.merchant_id)
        form.base_fields['external_job'].queryset = ExternalJob.objects.filter_by_merchant(obj.bulk.merchant_id)
        return form

    def has_add_permission(self, request):
        return False


admin.site.register(OrderPrototype, OrderPrototypeAdmin)


@admin.register(BulkDelayedUpload)
class BulkDelayedUploadAdmin(Select2FiltersMixin, admin.ModelAdmin):
    list_display = ('__str__', 'created', 'modified', 'status', 'method', 'uploaded_from', 'merchant', 'processed')
    list_filter = ('status', 'merchant', 'method')
    # inlines = (CSVOrdersFileAdmin,)
    inlines = (CSVOrdersFileAdmin, OrderPrototypeInlineAdmin)
    list_select_related = ('merchant', )

    raw_id_fields = ('merchant', )
    autocomplete_lookup_fields = {
        'fk': ['merchant', ],
    }

    # This is faster then annotation
    def processed(self, obj):
        obj.update_state()
        return obj.state_params['processed']

    def get_queryset(self, request):
        qs = super(BulkDelayedUploadAdmin, self).get_queryset(request)
        return qs.select_related('csv_file')


class TerminateCodeForm(forms.ModelForm):
    class Meta:
        model = TerminateCode
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super(TerminateCodeForm, self).__init__(*args, **kwargs)
        instance = kwargs.get('instance')
        if instance:
            self.fields['type'].disabled = True
            if instance.code == settings.TERMINATE_CODES[instance.type]['OTHER']:
                self.fields['merchant'].disabled = True
                self.fields['name'].disabled = True

    def clean(self):
        if not bool(self.instance.id):
            merchant = self.cleaned_data.get('merchant')
            code_type = self.cleaned_data.get('type')
            status_codes_count = TerminateCode.objects.filter(merchant=merchant, type=code_type).count()
            if code_type == TerminateCode.TYPE_SUCCESS and merchant and not merchant.advanced_completion_enabled:
                raise forms.ValidationError(SUCCESS_CODES_DISABLED_MSG)
            if code_type and status_codes_count >= settings.TERMINATE_CODES[code_type]['OTHER']:
                raise forms.ValidationError('Too many %s codes.' % (code_type, ))


@admin.register(TerminateCode)
class TerminateCodeAdmin(RemoveDeleteActionMixin, Select2FiltersMixin, TrackableModelAdmin):
    list_display = ('code', 'name', 'type', 'merchant', 'is_comment_necessary')
    fields = ('code', 'name', 'type', 'merchant', 'is_comment_necessary', 'email_notification_recipient')
    readonly_fields = ('code', 'is_comment_necessary')
    list_filter = ('merchant', 'type')
    form = TerminateCodeForm
    actions = ['custom_delete_selected']

    raw_id_fields = ('merchant', )
    autocomplete_lookup_fields = {
        'fk': ['merchant', ],
    }

    def custom_delete_selected(self, request, queryset):
        other_codes = (
            settings.TERMINATE_CODES[TerminateCode.TYPE_SUCCESS]['OTHER'],
            settings.TERMINATE_CODES[TerminateCode.TYPE_ERROR]['OTHER'],
        )
        if queryset.filter(code__in=other_codes).exists():
            self.message_user(request, 'You can\'t remove "other" code.', level=messages.ERROR)
            return None
        if queryset.count() == 1:
            message_bit = "1 code was"
        else:
            message_bit = "{count} codes were".format(count=queryset.count())
        queryset.delete()
        self.message_user(request, "%s successfully deleted." % message_bit, level=messages.SUCCESS)
    custom_delete_selected.short_description = "Delete selected codes"


class InlineTerminationCodeAdmin(admin.TabularInline):
    model = TerminateCode
    extra = 1
    can_delete = False
    fields = ('code', 'name', 'type', 'email_notification_recipient')
    readonly_fields = ('code', 'type')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(OrderLocation)
class OrderLocationAdmin(admin.ModelAdmin):
    list_display = ('location', 'address', 'raw_address', 'description', )
    search_fields = ('address', 'raw_address', 'location', 'deliver__order_id', 'deliver__title')
    ordering = ('-created_at',)


@admin.register(Barcode)
class BarcodeAdmin(admin.ModelAdmin):
    list_display = ('code_data', 'order_id', 'required', 'scanned_at_the_warehouse', 'scanned_upon_delivery')
    search_fields = ('code_data', 'order__id')
    list_filter = ('required', 'scanned_at_the_warehouse', 'scanned_upon_delivery')
    list_select_related = ('order', )
    raw_id_fields = list_select_related


@admin.register(ConcatenatedOrder)
class ConcatenatedOrderAdmin(OrderAdmin):
    readonly_fields = OrderAdmin.readonly_fields + ('list_concatenated_orders_link', 'list_available_orders_link')
    ordering = ('-deliver_before',)

    def get_queryset(self, request):
        return ConcatenatedOrder.all_objects.all().select_related(*self.list_select_related).prefetch_related(
            Prefetch('order_confirmation_photos', queryset=OrderConfirmationPhoto.objects.filter(image__isnull=False)),
            Prefetch('pre_confirmation_photos', queryset=OrderPreConfirmationPhoto.objects.filter(image__isnull=False)),
            Prefetch('pick_up_confirmation_photos',
                     queryset=OrderPickUpConfirmationPhoto.objects.filter(image__isnull=False))
        )

    def update_object(self, request, object_id, form_url, extra_context):
        instance = self.get_object(request, object_id)
        with track_fields_on_change(list(instance.orders.all()), initiator=request.user, sender=co_auto_processing):
            with track_fields_on_change(instance, initiator=request.user, sender=self):
                result = super(TrackableModelAdmin, self).changeform_view(request, object_id, form_url, extra_context)
        return result

    def list_concatenated_orders_link(self, model_object):
        opts = Order._meta
        iri = f'admin:{opts.app_label}_{opts.model_name}_changelist'

        params = {}
        if model_object.pk is not None:
            params['concatenated_order'] = model_object.pk

        params = urlencode(params)
        local_uri = reverse(iri) + '?' + params

        return mark_safe(f"<a href='{local_uri}' target='_blank'>Concatenated orders</a>")

    list_concatenated_orders_link.short_description = 'Orders'

    def list_available_orders_link(self, model_object):
        opts = Order._meta
        iri = f'admin:{opts.app_label}_{opts.model_name}_changelist'

        params = {}
        if model_object.pk is not None:
            params['concatenated_order__isnull'] = True
            params['merchant__id'] = model_object.merchant_id
            params['status__exact'] = model_object.status
            params['deleted__exact'] = 0

            if model_object.driver_id is None:
                params['driver__isnull'] = True
            else:
                params['driver__id'] = model_object.driver_id

            from datetime import datetime, timedelta
            deliver_day = datetime.combine(model_object.deliver_day, datetime.min.time())
            deliver_day = model_object.merchant.timezone.localize(deliver_day)
            params['deliver_before__gte'] = deliver_day
            params['deliver_before__lte'] = deliver_day + timedelta(days=1)

        params = urlencode(params)
        local_uri = reverse(iri) + '?' + params

        return mark_safe(f"<a href='{local_uri}' target='_blank'>Available orders</a>")

    list_available_orders_link.short_description = 'Orders'
