from datetime import datetime

from django.db.models import F, Q

import dateutil

from delivery.celery import app
from notification.models import MerchantMessageTemplate
from reporting.models import ExportReportInstance
from tasks.csv_parsing import OrderQSWriter, SurveyResultsQSWriter

from ..models import Merchant, SubBranding
from ..models.mixins import MerchantTypes
from ..utils import ReportsFrequencySettingsMixin


def send_report(frequency, merch, email, sub_brand=None):
    time_range = ReportsFrequencySettingsMixin.REPORT_FREQUENCY_RANGES[frequency]
    to_ = datetime.now(merch.timezone).replace(hour=0, minute=0, second=0, microsecond=0)
    from_ = to_ - dateutil.relativedelta.relativedelta(**time_range)
    report_params = {
        'date_from': from_,
        'date_to': to_,
        'merchant': merch if not merch.merchant_group_id else merch.merchant_group.merchants.all()
    }
    email_context = report_params.copy()

    if sub_brand:
        report_params['sub_branding_id'] = sub_brand.id
        email_context['merchant'] = sub_brand

    report_instance = ExportReportInstance.objects.create(merchant=merch)
    report_instance.build_csv_report(OrderQSWriter, report_params)
    merch.send_report_email(
        report_instance=report_instance, email=email,
        extra_context=email_context, template=MerchantMessageTemplate.JOBS_DAILY_REPORT,
    )


@app.task
def send_merchant_jobs_report(frequency):
    merchants = Merchant.objects \
        .filter(
            reports_frequency=frequency,
            templates__template_type=MerchantMessageTemplate.JOBS_DAILY_REPORT,
            templates__enabled=True
        ) \
        .exclude(jobs_export_email='').select_related('merchant_group') \
        .filter(Q(merchant_group__isnull=True)
                | (Q(merchant_group__isnull=False) & Q(merchant_group__core_merchant_id__isnull=True))
                | (Q(merchant_group__isnull=False) & Q(id=F('merchant_group__core_merchant_id'))))

    for merchant in merchants:
        send_report(frequency, merchant, merchant.jobs_export_email)


@app.task
def send_sub_brand_jobs_report(frequency):
    sub_brands = SubBranding.objects\
        .filter(
            reports_frequency=frequency,
            merchant__templates__template_type=MerchantMessageTemplate.JOBS_DAILY_REPORT,
            merchant__templates__enabled=True
        )\
        .exclude(jobs_export_email='').select_related('merchant')

    for sub_brand in sub_brands:
        send_report(frequency, sub_brand.merchant, sub_brand.jobs_export_email, sub_brand)


@app.task
def send_reports(frequency):
    if frequency == ReportsFrequencySettingsMixin.EVERY_TWO_WEEKS:
        week_number = int(datetime.today().strftime("%U"))
        if week_number % 2:
            return

    send_merchant_jobs_report.delay(frequency)
    send_sub_brand_jobs_report.delay(frequency)
    send_merchant_survey_report.delay(frequency)
    send_sub_brand_survey_report.delay(frequency)


@app.task
def send_merchant_survey_report(frequency):
    merchants = Merchant.objects\
        .filter(
            survey_reports_frequency=frequency,
            templates__template_type=MerchantMessageTemplate.SURVEY_REPORT,
            templates__enabled=True
        )\
        .exclude(survey_export_email='')
    for merchant in merchants:
        send_survey_report(frequency, merchant, merchant.survey_export_email)


@app.task
def send_sub_brand_survey_report(frequency):
    sub_brands = SubBranding.objects \
        .filter(
            survey_reports_frequency=frequency,
            merchant__templates__template_type=MerchantMessageTemplate.SURVEY_REPORT,
            merchant__templates__enabled=True
        ) \
        .exclude(survey_export_email='').select_related('merchant')
    for sub_brand in sub_brands:
        send_survey_report(frequency, sub_brand.merchant, sub_brand.survey_export_email, sub_brand)


def send_survey_report(frequency, merchant, email, sub_brand=None):
    survey = sub_brand.customer_survey if sub_brand else merchant.customer_survey
    if not survey:
        return

    time_range = ReportsFrequencySettingsMixin.REPORT_FREQUENCY_RANGES[frequency]
    to_ = datetime.now(merchant.timezone).replace(hour=0, minute=0, second=0, microsecond=0)
    from_ = to_ - dateutil.relativedelta.relativedelta(**time_range)
    report_params = {
        'survey': survey,
        'date_from': from_,
        'date_to': to_,
        'merchant': merchant,
    }
    email_context = report_params.copy()

    if sub_brand:
        report_params['sub_branding_id'] = sub_brand.id
        email_context['merchant'] = sub_brand

    file_name = 'SurveyResults_{}'.format(survey.title)
    report_instance = ExportReportInstance.objects.create(merchant=merchant)
    report_instance.build_csv_report(SurveyResultsQSWriter, report_params, file_name=file_name)
    merchant.send_report_email(
        report_instance=report_instance, email=email,
        extra_context=email_context, template=MerchantMessageTemplate.SURVEY_REPORT,
    )


@app.task
def export_miele_survey_results():
    upload_default_survey_reports.delay()
    upload_special_survey_reports.delay()


@app.task
def upload_default_survey_reports():
    merchants = Merchant.objects.filter(merchant_type=MerchantTypes.MERCHANT_TYPES.MIELE_DEFAULT) \
        .exclude(survey_export_directory='')
    for merchant in merchants:
        upload_survey_report(merchant)


@app.task
def upload_special_survey_reports():
    sub_brands = SubBranding.objects.filter(merchant__merchant_type=MerchantTypes.MERCHANT_TYPES.MIELE_SURVEY) \
        .exclude(merchant__survey_export_directory='').select_related('merchant')
    for sub_brand in sub_brands:
        upload_survey_report(sub_brand.merchant, sub_brand)


def upload_survey_report(merchant, sub_brand=None):
    survey = sub_brand.customer_survey if sub_brand else merchant.customer_survey
    if not survey:
        return

    to_ = datetime.now(merchant.timezone).replace(hour=0, minute=0, second=0, microsecond=0)
    survey_passed_from = to_ - dateutil.relativedelta.relativedelta(days=1)
    # survey can be passed within 48 hours after job completion, so we increase search bounds for jobs
    from_ = survey_passed_from - dateutil.relativedelta.relativedelta(days=2)

    report_params = {
        'survey': survey,
        'date_from': from_,
        'date_to': to_,
        'merchant': merchant,
        'extra_conditions': Q(**{'customer_survey__created_at__gte': survey_passed_from,
                                 'customer_survey__created_at__lte': to_}),
        'period': {
            'from': survey_passed_from,
            'to': to_
        }
    }
    if sub_brand:
        report_params['sub_branding_id'] = sub_brand.id

    file_name = 'SurveyResults_{}'.format(survey.title)
    report_instance = ExportReportInstance.objects.create(merchant=merchant)
    report_instance.build_csv_report(SurveyResultsQSWriter, report_params, file_name=file_name)
    report_instance.refresh_from_db()

    merchant.upload_report(report_instance)


__all__ = ['send_reports', 'send_merchant_jobs_report', 'send_sub_brand_jobs_report',
           'send_merchant_survey_report', 'send_sub_brand_survey_report', 'export_miele_survey_results',
           'upload_default_survey_reports', 'upload_special_survey_reports']
