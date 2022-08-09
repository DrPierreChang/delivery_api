import re
from datetime import datetime, timedelta

from django.test import override_settings
from django.utils import timezone

from rest_framework.test import APITestCase

from mock import mock

from base.factories import ManagerFactory
from merchant.celery_tasks import send_merchant_jobs_report, send_sub_brand_jobs_report
from merchant.factories import MerchantFactory, MerchantGroupFactory, SubBrandingFactory
from merchant.models import Merchant, SubBranding
from notification.models import MerchantMessageTemplate, TemplateEmailMessage
from tasks.tests.factories import OrderFactory


class JobReportsSendingTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.template_type = MerchantMessageTemplate.JOBS_DAILY_REPORT
    
    def setUp(self):
        self.merchant = MerchantFactory(jobs_export_email='merchant@test.com', merchant_group=None)
        self.merchant.templates.filter(template_type=self.template_type).update(enabled=True)
        self.manager = ManagerFactory(merchant=self.merchant)
        self.sub_brand = SubBrandingFactory(merchant=self.merchant, jobs_export_email='subbrand@test.com')

    @mock.patch('notification.celery_tasks.send_template_notification.apply_async')
    def test_merchant_jobs_report_disabled(self, send_email_patch):
        self.merchant.templates.filter(template_type=self.template_type).update(enabled=False)
        send_merchant_jobs_report(Merchant.DAILY)
        self.assertFalse(send_email_patch.called)

    @mock.patch('notification.celery_tasks.send_template_notification.apply_async')
    def test_merchant_jobs_report_without_export_email(self, send_email_patch):
        self.merchant.jobs_export_email = ''
        self.merchant.save()
        send_merchant_jobs_report(Merchant.DAILY)
        self.assertFalse(send_email_patch.called)

    @mock.patch('notification.celery_tasks.send_template_notification.apply_async')
    def test_jobs_report_merchant_is_core(self, send_email_patch):
        self.merchant_group = MerchantGroupFactory(core_merchant=None)
        self.extra_merchant = MerchantFactory(jobs_export_email='extramerch@test.com')
        self.extra_merchant.templates\
            .filter(template_type=MerchantMessageTemplate.JOBS_DAILY_REPORT)\
            .update(enabled=True)

        self.merchant.merchant_group = self.merchant_group
        self.extra_merchant.merchant_group = self.merchant_group
        self.merchant.save()
        self.extra_merchant.save()
        send_merchant_jobs_report(Merchant.DAILY)
        self.assertTrue(send_email_patch.called)
        self.assertEqual(send_email_patch.call_count, 2)

        self.merchant_group.core_merchant = self.merchant
        self.merchant_group.save()   
        send_merchant_jobs_report(Merchant.DAILY)
        self.assertTrue(send_email_patch.called)
        self.assertEqual(send_email_patch.call_count, 3)

    @mock.patch('notification.celery_tasks.send_template_notification.apply_async')
    @mock.patch('django.core.files.storage.default_storage.save')
    @override_settings(DEFAULT_DRIVER_ICON='nonexistent_image.png')
    def test_merchant_group_jobs_report_exists(self, storage_mock, send_email_patch):
        self.merchant_group = MerchantGroupFactory(core_merchant=None)
        self.extra_merchant = MerchantFactory(jobs_export_email='extramerch@test.com')

        self.merchant.merchant_group = self.merchant_group
        self.extra_merchant.merchant_group = self.merchant_group
        self.merchant.save()
        self.extra_merchant.save()
        self.merchant_group.core_merchant = self.merchant
        self.merchant_group.save()

        day_before = timezone.now() - timedelta(days=1)
        with mock.patch('django.utils.timezone.now', mock.Mock(return_value=day_before)):
            OrderFactory.create_batch(size=5, merchant=self.merchant, manager=self.manager)

        report_name = 'merchant_group_report.csv'
        storage_mock.return_value = report_name

        send_merchant_jobs_report(Merchant.DAILY)
        self.assertTrue(send_email_patch.called)
        send_email_patch.assert_called_once()

        model_name, obj_id = send_email_patch.call_args[0][0]
        self.assertEqual(model_name, TemplateEmailMessage.__name__)

        email_msg = TemplateEmailMessage.objects.get(id=obj_id)
        self.assertEqual(email_msg.template.template_type, self.template_type)

        report_link = re.split('[\n]+', email_msg.text.strip())[-1]
        file_name = report_link.split('/')[-1]
        self.assertEqual(report_name, file_name)

        report_instance_qs = self.merchant.exportreportinstance_set.filter(file=file_name)
        self.assertTrue(report_instance_qs.exists())

    @mock.patch('notification.celery_tasks.send_template_notification.apply_async')
    def test_merchant_jobs_report_empty(self, send_email_patch):
        send_merchant_jobs_report(Merchant.DAILY)
        self.assertTrue(send_email_patch.called)
        send_email_patch.assert_called_once()

        model_name, obj_id = send_email_patch.call_args[0][0]
        self.assertEqual(model_name, TemplateEmailMessage.__name__)

        email_msg = TemplateEmailMessage.objects.get(id=obj_id)
        self.assertEqual(email_msg.template.template_type, self.template_type)

        email_text = 'Hello, {merchant_name}!\n\n    ' \
                     'There were no jobs to generate the Periodical Report on {date}\n\n\n\n'
        date = datetime.strftime(datetime.now(self.merchant.timezone) - timedelta(days=1), '%b %d, %Y')
        self.assertEqual(email_msg.text, email_text.format(merchant_name=self.merchant.name, date=date))

    def _send_merchant_job_report(self, frequency, days_delta, file_name, storage_mock, send_email_mock):
        week_number = int(datetime.today().strftime("%U"))
        if frequency == Merchant.EVERY_TWO_WEEKS and week_number % 2:
            self.assertFalse(send_email_mock.called)
            return
        
        self.merchant.reports_frequency = frequency
        self.merchant.save()

        day_before = timezone.now() - timedelta(days=days_delta)
        with mock.patch('django.utils.timezone.now', mock.Mock(return_value=day_before)):
            OrderFactory.create_batch(size=5, merchant=self.merchant, manager=self.manager)

        report_name = file_name
        storage_mock.return_value = report_name

        send_merchant_jobs_report(frequency)
        self.assertTrue(send_email_mock.called)
        send_email_mock.assert_called_once()

        model_name, obj_id = send_email_mock.call_args[0][0]
        self.assertEqual(model_name, TemplateEmailMessage.__name__)

        email_msg = TemplateEmailMessage.objects.get(id=obj_id)
        self.assertEqual(email_msg.template.template_type, self.template_type)

        report_link = re.split('[\n]+', email_msg.text.strip())[-1]
        file_name = report_link.split('/')[-1]
        self.assertEqual(report_name, file_name)

        report_instance_qs = self.merchant.exportreportinstance_set.filter(file=file_name)
        self.assertTrue(report_instance_qs.exists())

    @mock.patch('notification.celery_tasks.send_template_notification.apply_async')
    def test_subbrand_jobs_report_disabled(self, send_email_patch):
        self.merchant.templates.filter(template_type=self.template_type).update(enabled=False)
        send_sub_brand_jobs_report(SubBranding.DAILY)
        self.assertFalse(send_email_patch.called)

    @mock.patch('notification.celery_tasks.send_template_notification.apply_async')
    def test_subbrand_jobs_report_without_export_email(self, send_email_patch):
        self.sub_brand.jobs_export_email = ''
        self.sub_brand.save()
        send_sub_brand_jobs_report(frequency=SubBranding.DAILY)
        self.assertFalse(send_email_patch.called)

    def _send_subbrand_job_report(self, frequency, days_delta, file_name, storage_mock, send_email_mock):
        week_number = int(datetime.today().strftime("%U"))
        if frequency == SubBranding.EVERY_TWO_WEEKS and week_number % 2:
            self.assertFalse(send_email_mock.called)
            return

        self.sub_brand.reports_frequency = frequency
        self.sub_brand.save()

        day_before = timezone.now() - timedelta(days=days_delta)
        with mock.patch('django.utils.timezone.now', mock.Mock(return_value=day_before)):
            OrderFactory.create_batch(
                size=5, merchant=self.merchant,
                manager=self.manager, sub_branding=self.sub_brand
            )

        report_name = file_name
        storage_mock.return_value = report_name

        send_sub_brand_jobs_report(frequency)
        self.assertTrue(send_email_mock.called)
        send_email_mock.assert_called_once()

        model_name, obj_id = send_email_mock.call_args[0][0]
        self.assertEqual(model_name, TemplateEmailMessage.__name__)

        email_msg = TemplateEmailMessage.objects.get(id=obj_id)
        self.assertEqual(email_msg.template.template_type, self.template_type)

        report_link = re.split('[\n]+', email_msg.text.strip())[-1]
        file_name = report_link.split('/')[-1]
        self.assertEqual(report_name, file_name)

        report_instance_qs = self.merchant.exportreportinstance_set.filter(file=file_name)
        self.assertTrue(report_instance_qs.exists())

    @mock.patch('notification.celery_tasks.send_template_notification.apply_async')
    @mock.patch('django.core.files.storage.default_storage.save')
    @override_settings(DEFAULT_DRIVER_ICON='nonexistent_image.png')
    def test_subbrand_daily_jobs_report(self, storage_mock, send_email_mock):
        self._send_subbrand_job_report(
            SubBranding.DAILY, 1, 'daily_report.csv',
            storage_mock, send_email_mock
        )

    @mock.patch('notification.celery_tasks.send_template_notification.apply_async')
    @mock.patch('django.core.files.storage.default_storage.save')
    @override_settings(DEFAULT_DRIVER_ICON='nonexistent_image.png')
    def test_subbrand_weekly_jobs_report(self, storage_mock, send_email_mock):
        self._send_subbrand_job_report(
            SubBranding.WEEKLY, 5, 'weekly_report.csv',
            storage_mock, send_email_mock
        )

    @mock.patch('notification.celery_tasks.send_template_notification.apply_async')
    @mock.patch('django.core.files.storage.default_storage.save')
    @override_settings(DEFAULT_DRIVER_ICON='nonexistent_image.png')
    def test_subbrand_two_weeks_jobs_report(self, storage_mock, send_email_mock):
        self._send_subbrand_job_report(
            SubBranding.EVERY_TWO_WEEKS, 13, '2_weeks_report.csv',
            storage_mock, send_email_mock
        )

    @mock.patch('notification.celery_tasks.send_template_notification.apply_async')
    @mock.patch('django.core.files.storage.default_storage.save')
    @override_settings(DEFAULT_DRIVER_ICON='nonexistent_image.png')
    def test_subbrand_monthly_jobs_report(self, storage_mock, send_email_mock):
        self._send_subbrand_job_report(
            SubBranding.MONTHLY, 20, 'monthly_report.csv',
            storage_mock, send_email_mock
        )

    @mock.patch('notification.celery_tasks.send_template_notification.apply_async')
    @mock.patch('django.core.files.storage.default_storage.save')
    @override_settings(DEFAULT_DRIVER_ICON='nonexistent_image.png')
    def test_merchant_daily_jobs_report(self, storage_mock, send_email_mock):
        self._send_merchant_job_report(
            Merchant.DAILY, 1, 'merchant_daily_report.csv',
            storage_mock, send_email_mock
        )

    @mock.patch('notification.celery_tasks.send_template_notification.apply_async')
    @mock.patch('django.core.files.storage.default_storage.save')
    @override_settings(DEFAULT_DRIVER_ICON='nonexistent_image.png')
    def test_merchant_weekly_jobs_report(self, storage_mock, send_email_mock):
        self._send_merchant_job_report(
            Merchant.WEEKLY, 5, 'merchant_weekly_report.csv',
            storage_mock, send_email_mock
        )

    @mock.patch('notification.celery_tasks.send_template_notification.apply_async')
    @mock.patch('django.core.files.storage.default_storage.save')
    @override_settings(DEFAULT_DRIVER_ICON='nonexistent_image.png')
    def test_merchant_two_weeks_jobs_report(self, storage_mock, send_email_mock):
        self._send_merchant_job_report(
            Merchant.EVERY_TWO_WEEKS, 13, 'merchant_2_weeks_report.csv',
            storage_mock, send_email_mock
        )

    @mock.patch('notification.celery_tasks.send_template_notification.apply_async')
    @mock.patch('django.core.files.storage.default_storage.save')
    @override_settings(DEFAULT_DRIVER_ICON='nonexistent_image.png')
    def test_merchant_monthly_jobs_report(self, storage_mock, send_email_mock):
        self._send_merchant_job_report(
            Merchant.MONTHLY, 20, 'merchant_monthly_report.csv',
            storage_mock, send_email_mock
        )
