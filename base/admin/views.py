from __future__ import absolute_import

from urllib.parse import quote as urlquote

from django.contrib import messages
from django.contrib.admin.utils import quote
from django.db.models import BooleanField, Case, Subquery, When
from django.http import JsonResponse
from django.urls import reverse, reverse_lazy
from django.utils.html import format_html
from django.views.generic import FormView

from merchant.models import Merchant, SubBranding

from ..models import Member
from .forms import CMSWeeklyUsageReportForm, DriverScheduleImportForm, PhoneNumberForm


class SMSTestView(FormView):
    template_name = 'admin/test_sms.html'
    form_class = PhoneNumberForm

    def form_valid(self, form):
        form.send_sms()
        context_data = self.get_context_data()
        context_data['success_message'] = 'Successfully sent'
        return self.render_to_response(context_data)


class CMSWeeklyUsageReport(FormView):
    template_name = 'admin/weekly_report.html'
    form_class = CMSWeeklyUsageReportForm
    report_date = None

    def form_valid(self, form):
        form.send_email()
        context_data = self.get_context_data()
        context_data['success_message'] = 'Successfully sent'
        return self.render_to_response(context_data)


class DriverScheduleImport(FormView):
    template_name = 'admin/drivers_schedule_import.html'
    form_class = DriverScheduleImportForm
    success_url = reverse_lazy('admin:drivers_schedule_import')
    extra_context = {
        'title': "Bulk upload of drivers' schedule and capacity"
    }

    def form_valid(self, form):
        bulk = form.save_schedule(self.request)
        bulk_opts = bulk._meta
        bulk_url = reverse(f'admin:{bulk_opts.app_label}_{bulk_opts.model_name}_change', args=(quote(bulk.pk),))
        bulk_repr = format_html('<a href="{}">{}</a>', urlquote(bulk_url), bulk)

        message = format_html(
            'The file has been uploaded successfully, but is still being processed. Details can be seen here: "{}"',
            bulk_repr,
        )
        messages.warning(self.request, message)

        return super().form_valid(form)


def get_group_manager_merchants(request, *args, **kwargs):
    merchants, sub_brands, merchant_select_disabled, sub_brand_select_disabled = [], [], True, True

    role = request.GET.get('role', 0)
    if int(role) == Member.GROUP_MANAGER:
        merchant_select_disabled = False
        sub_brand_select_disabled = False
        merchants = list(Merchant.objects.all().values('id', 'name'))
        sub_brands = list(SubBranding.objects.all().values('id', 'name'))
    elif int(role) in Member.ROLES_WITH_MANY_MERCHANTS:
        merchant_select_disabled = False
        merchants = list(Merchant.objects.all().values('id', 'name'))

    merchant_ids, sub_brand_ids = request.GET.getlist('merchant_ids[]', []), request.GET.getlist('sub_brand_ids[]', [])
    document_load = request.GET.get('document_load', False)
    if not document_load:
        unselected_sub_brands = SubBranding.objects.filter(merchant_id__in=Subquery(
            SubBranding.objects.filter(id__in=sub_brand_ids).values_list('merchant_id', flat=True))
        ).exclude(id__in=sub_brand_ids)
    elif sub_brand_ids and document_load:
        unselected_sub_brands = SubBranding.objects.filter(merchant_id__in=merchant_ids).exclude(id__in=sub_brand_ids)
    else:
        unselected_sub_brands = SubBranding.objects.filter(merchant_id__in=merchant_ids)

    if merchant_ids:
        sub_brands = list(SubBranding.objects.filter(merchant_id__in=merchant_ids)
                          .annotate(chosen=Case(When(id__in=unselected_sub_brands, then=False), default=True,
                                                output_field=BooleanField())).values('id', 'name', 'chosen'))

    return JsonResponse(
        {
            'sub_brandings': sub_brands,
            'merchants': merchants,
            'merchant_select_disabled': merchant_select_disabled,
            'sub_brand_select_disabled': sub_brand_select_disabled
        },
        safe=True,
    )
