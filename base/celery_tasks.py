from django.utils import timezone

from celery.schedules import crontab
from celery.task import periodic_task
from constance import config

from base.utils import weekly_usage_context
from notification.mixins import MessageTemplateStatus
from notification.models import MerchantMessageTemplate, TemplateEmailMessage


@periodic_task(run_every=crontab(day_of_week='monday', hour=0, minute=0), ignore_result=True)
def weekly_usage_report(report_date=None, emails=[]):
    emails = emails or config.EMAILS_FOR_WEEKLY_REPORTS
    now = report_date or timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

    context = weekly_usage_context(report_date=now)
    template = MerchantMessageTemplate.objects.filter(template_type=MessageTemplateStatus.WEEKLY_REPORT).last()

    for email in emails:
        message = TemplateEmailMessage.objects.create(email=email, template=template, context=context)
        message.send()
