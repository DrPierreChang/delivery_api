from celery.schedules import crontab

from delivery.celery import app

from ..utils import ReportsFrequencySettingsMixin
from .reports import export_miele_survey_results, send_reports


@app.on_after_finalize.connect
def setup_periodic_tasks(sender, **kwargs):
    # Send reports every day
    sender.add_periodic_task(
        crontab(hour=4, minute=30),
        send_reports.s(ReportsFrequencySettingsMixin.DAILY)
    )
    # Send reports every week
    sender.add_periodic_task(
        crontab(hour=0, minute=0, day_of_week=1),
        send_reports.s(ReportsFrequencySettingsMixin.WEEKLY)
    )
    # Send reports every 2 weeks
    sender.add_periodic_task(
        crontab(hour=0, minute=0, day_of_week=1),
        send_reports.s(ReportsFrequencySettingsMixin.EVERY_TWO_WEEKS)
    )
    # Send reports every month
    sender.add_periodic_task(
        crontab(hour=0, minute=0, day_of_month=1),
        send_reports.s(ReportsFrequencySettingsMixin.MONTHLY)
    )

    # Upload Miele survey reports on remote SFTP server daily
    sender.add_periodic_task(
        crontab(hour=0, minute=0),
        export_miele_survey_results.s()
    )


__all__ = ['setup_periodic_tasks', ]
