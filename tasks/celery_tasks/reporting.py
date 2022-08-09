from __future__ import absolute_import, unicode_literals

import sentry_sdk

from base.models import Member
from delivery.celery import app
from reporting.models import ExportReportInstance
from tasks.csv_parsing import OrderQSWriter


@app.task()
def generate_report_file(task_id, initiator_id, params, format_):
    report_instance = None
    try:
        initiator = Member.objects.select_related('merchant').get(id=initiator_id)
        report_instance = ExportReportInstance.objects.select_related('merchant').get(id=task_id)
        report_instance.initiator = initiator
        report_instance.save()

        report_instance.prepare_file(params, file_name=None, unique_name=True)

        writer = OrderQSWriter(report_instance, params)

        report_instance.begin(writer, format_)
        report_instance.complete()
    except Exception as ex:
        sentry_sdk.capture_exception(ex)
        if report_instance:
            report_instance.fail(message=str(ex) or 'Error while composing report.')
            raise
    finally:
        report_instance.save()
