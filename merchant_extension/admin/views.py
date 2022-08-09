from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.views.generic import FormView

from merchant.models import Merchant, SubBranding
from radaro_utils.utils import get_date_format
from reporting.models import ExportReportInstance
from tasks.csv_parsing import SurveyResultsQSWriter

from .forms import CMSSurveyResultsForm


def get_survey_merchants_view(request, *args, **kwargs):
    survey_id = request.GET.get('survey')
    merchant_ids = request.GET.getlist('merchant_ids[]', [])
    if not survey_id:
        merchants, sub_brands = [], []
    else:
        sub_brands = SubBranding.objects.filter(
                Q(customer_survey_id=survey_id)
                | Q(orders__customer_survey__checklist_id=survey_id),
            ).distinct()

        if merchant_ids:
            sub_brands = list(sub_brands.filter(merchant_id__in=merchant_ids).values('id', 'name'))
            merchants = []

        else:
            merchants = list(Merchant.objects.filter(
                Q(customer_survey_id=survey_id)
                | Q(orders__customer_survey__checklist_id=survey_id),
            ).distinct().values('id', 'name'))
            sub_brands = list(sub_brands.values('id', 'name'))

    return JsonResponse({'merchants': merchants, 'sub_brands': sub_brands}, safe=True)


class SurveyResultsDownloadCSVMixin(object):
    def generate_response(self, data):
        report_instance = ExportReportInstance.objects.create(
            initiator=self.request.user,
            merchant=self.request.user.current_merchant,
        )
        file_name = 'SurveyResults_{}'.format(data['survey'].title)
        report_instance.build_csv_report(
            SurveyResultsQSWriter, data,
            file_name=file_name, unique_name=False
        )
        with default_storage.open(report_instance.file.name, 'rb') as report:
            report_file_name = report_instance.file.name.split('/')[-1]
            response = HttpResponse(report, content_type='text/csv')
            response['Content-Disposition'] = 'attachment; filename="{0}"'.format(report_file_name)
            return response


class CMSSurveyResultsView(SurveyResultsDownloadCSVMixin, FormView):
    template_name = 'admin/survey_results.html'
    form_class = CMSSurveyResultsForm

    def form_valid(self, form):
        params = {
            'merchant': form.cleaned_data['merchant'],
            'survey': form.cleaned_data['survey'],
            'sub_branding_id': form.cleaned_data['sub_brand'],
            'date_to': form.cleaned_data['date_to'],
            'date_from': form.cleaned_data['date_from']
        }
        return self.generate_response(params)

    def get_context_data(self, **kwargs):
        context = super(CMSSurveyResultsView, self).get_context_data(**kwargs)
        context['date_format'] = get_date_format()
        return context
