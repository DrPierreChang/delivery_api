from __future__ import absolute_import

from django import forms
from django.contrib import admin
from django.contrib.admin import widgets
from django.db import transaction

from base.models import Member
from merchant.models import Merchant
from radaro_utils.filters.date_filters import RadaroDateTimeRangeFilter
from radaro_utils.radaro_admin.admin import Select2FiltersMixin
from webhooks.models import MerchantAPIKey, MerchantAPIKeyEvents, MerchantAPIMultiKey, MerchantWebhookEvent


class APIKeyAdmin(Select2FiltersMixin, admin.ModelAdmin):
    readonly_fields = ('created', )
    list_display = ('key', 'merchant', 'available', 'created', 'name')
    list_filter = ('creator__merchant', )
    search_fields = ('key', 'name')

    raw_id_fields = ('merchant', )
    autocomplete_lookup_fields = {
        'fk': ['merchant', ],
    }

    def get_queryset(self, request):
        return super().get_queryset(request).filter(key_type=MerchantAPIKey.SINGLE)

    def get_form(self, request, obj=None, change=False, **kwargs):
        form = super().get_form(request, obj, change, **kwargs)
        form.base_fields['key_type'].choices = MerchantAPIKey.api_key_types[:1]
        form.base_fields['merchant'].required = True
        return form


class MultiKeyCreatorWidget(widgets.ForeignKeyRawIdWidget):
    def url_parameters(self):
        params = super().url_parameters()
        params['role__exact'] = Member.ADMIN
        return params


class MerchantAPIMultiKeyForm(forms.ModelForm):
    merchants = forms.ModelMultipleChoiceField(queryset=Merchant.objects.all())

    class Meta:
        model = MerchantAPIMultiKey
        exclude = ('merchant', )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['creator'].widget = MultiKeyCreatorWidget(MerchantAPIKey._meta.get_field('creator').remote_field,
                                                              admin.site)
        self.fields['key_type'].choices = MerchantAPIMultiKey.api_key_types[1:]
        if self.instance:
            self.fields['merchants'].initial = self.instance.merchants.all()

    def clean(self):
        if self.cleaned_data.get('creator'):
            if self.cleaned_data['creator'].role != Member.ADMIN:
                raise forms.ValidationError({'creator': 'Creator must be an admin manager.'})
            elif self.cleaned_data.get('merchants') \
                    and self.cleaned_data['creator'].merchant not in self.cleaned_data['merchants']:
                raise forms.ValidationError(
                    {'merchants': 'Creator is not the manager of any of the selected merchants.'}
                )
        return super().clean()

    def save(self, commit=False):
        key = super().save(commit)
        with transaction.atomic():
            if self.fields['merchants'].initial:
                self.fields['merchants'].initial.update(api_multi_key=None)
            key.save()
            self.cleaned_data['merchants'].update(api_multi_key=key)
        return key


class MerchantAPIMultiKeyAdmin(admin.ModelAdmin):
    form = MerchantAPIMultiKeyForm

    list_display = ('key', 'name', 'available', 'created', 'creator')
    search_fields = ('key', 'name')
    readonly_fields = ('created', )

    raw_id_fields = ('creator', )
    autocomplete_lookup_fields = {
        'fk': ['creator', ]
    }


class MerchantAPIKeyEventsAdmin(Select2FiltersMixin, admin.ModelAdmin):
    readonly_fields = ('request_path', 'request_method', 'response_status', 'happened_at',)
    list_display = ('merchant_api_key', 'get_merchant', 'happened_at', 'event_type', 'field', 'new_value',
                    'request_path', 'request_method', 'response_status',)
    list_filter = ('event_type', 'merchant_api_key__merchant', ('happened_at', RadaroDateTimeRangeFilter))
    search_fields = ('new_value', 'merchant_api_key__key', 'ip_address')

    raw_id_fields = ('merchant_api_key', )
    autocomplete_lookup_fields = {
        'fk': ['merchant_api_key', ],
    }

    def get_queryset(self, request):
        return super(MerchantAPIKeyEventsAdmin, self).get_queryset(request).select_related('merchant_api_key__merchant')

    def get_merchant(self, obj):
        if obj.merchant_api_key is not None:
            return obj.merchant_api_key.merchant
        return '-'
    get_merchant.short_description = 'Merchant'


class MerchantWebhookEventAdmin(Select2FiltersMixin, admin.ModelAdmin):
    list_display = ('happened_at', 'webhook_url', 'response_status', 'topic', 'order_id', 'order_title',
                    'external_id', 'merchant', 'sub_branding')
    readonly_fields = ('happened_at', 'webhook_url', 'response_status', 'topic', 'order_id', 'external_id', 'merchant',
                       'request_data', 'response_text', 'exception_detail', 'elapsed_time', 'order', 'sub_branding')
    list_filter = ('merchant', 'sub_branding', ('happened_at', RadaroDateTimeRangeFilter), 'topic')
    search_fields = ('webhook_url', 'order__order_id', 'order__title', 'order__external_job__external_id')
    list_select_related = ('merchant', 'sub_branding', 'order', 'order__external_job')

    def has_add_permission(self, request, obj=None):
        return False

    def order_id(self, event):
        return event.order.order_id if event.order else None

    def order_title(self, event):
        return event.order.title if event.order else None

    def external_id(self, event):
        return event.order.external_job.external_id if (event.order and event.order.external_job_id) else None


admin.site.register(MerchantAPIKey, APIKeyAdmin)
admin.site.register(MerchantAPIMultiKey, MerchantAPIMultiKeyAdmin)
admin.site.register(MerchantAPIKeyEvents, MerchantAPIKeyEventsAdmin)
admin.site.register(MerchantWebhookEvent, MerchantWebhookEventAdmin)
