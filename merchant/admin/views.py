from django.http import HttpResponse, JsonResponse
from django.template import loader

from base.models import Member
from merchant.models import Hub, Merchant
from radaro_utils.utils import get_date_format
from radaro_utils.views import GenericTimeFramedReport

from .forms import CMSMerchantReportForm


# Request through annotation and inner join with messages table and order table works VERY SLOW
def get_report_data(merchant_id, date_from, date_to):
    merchants = Merchant.objects.cms_report_data(merchant_id=merchant_id,
                                                 date_from=date_from,
                                                 date_to=date_to)

    return merchants


def get_drivers_and_hubs(request):
    merchant_id = request.GET.get('merchant')
    if not merchant_id:
        return JsonResponse(dict(drivers=[], hubs=[]), safe=True)
    drivers = list(Member.drivers.filter(merchant_id=merchant_id).values('id', 'first_name', 'last_name'))
    hubs = list(Hub.objects.filter(merchant_id=merchant_id).values('id', 'name'))
    return JsonResponse(dict(drivers=drivers, hubs=hubs), safe=True)


class CMSMerchantReportsView(GenericTimeFramedReport):
    template_name = 'admin/merchant_report.html'

    def get_context_data(self, **kwargs):
        context = super(CMSMerchantReportsView, self).get_context_data(**kwargs)
        merchant = None
        date_format = get_date_format()
        form = CMSMerchantReportForm(initial={'date_from': self.date_from.strftime(date_format),
                                              'date_to': self.date_to.strftime(date_format)})

        if self.request.GET:
            form = CMSMerchantReportForm(self.request.GET)
            if form.is_valid():
                self.date_from = form.cleaned_data.get('date_from')
                self.date_to = form.cleaned_data.get('date_to')
                merchant = form.cleaned_data.get('merchant', None)

        merchant_id = getattr(merchant, 'id', None)
        context['form'] = form
        context['merchants'] = get_report_data(merchant_id, self.date_from, self.date_to)
        return context


class GenerateCSVReportView(GenericTimeFramedReport):
    template_name = 'admin/csv_report_template.html'

    def get(self, request, *args, **kwargs):
        merchant_id = request.GET.get('merchant', None)
        merchants = get_report_data(merchant_id, self.date_from, self.date_to)

        response = HttpResponse(content_type='text/csv')
        date_format = get_date_format()
        filename = "report_from_{}_to_{}.csv".format(
            self.date_from.strftime(date_format),
            self.date_to.strftime(date_format)
        )
        response['Content-Disposition'] = 'attachment; filename="{0}"'.format(filename)
        csv_header = ('Merchant',
                      'Merchant ID',
                      'Invites SMS to driver',
                      'Pin codes SMS to driver',
                      'Total SMS to driver',
                      'Delivery day SMS to customer',
                      'Job started SMS to customer',
                      'Job failed SMS to customer',
                      'Reminder(1 h) SMS to customer',
                      'Reminder(24 h) SMS to customer',
                      'Total SMS to customer',
                      'Jobs created')
        csv_data = [(
            merchant.name,
            merchant.id,
            merchant.sms_invitation,
            merchant.sms_invitation_complete,
            merchant.total_driver_sms,
            merchant.sms_order_upcoming_delivery,
            merchant.sms_order_in_progress,
            merchant.sms_order_terminated,
            merchant.sms_order_follow_up,
            merchant.sms_order_follow_up_reminder,
            merchant.total_customer_sms,
            merchant.jobs
        ) for merchant in merchants]
        template = loader.get_template(self.template_name)
        context = {
            'header': csv_header,
            'data': csv_data,
        }

        response.write(template.render(context))
        return response
