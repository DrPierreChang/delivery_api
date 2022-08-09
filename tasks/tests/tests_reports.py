from __future__ import absolute_import, unicode_literals

from datetime import timedelta

from django.db import transaction
from django.test import override_settings, tag
from django.utils import timezone

from rest_framework.status import HTTP_200_OK

from six.moves import xrange

from radaro_utils.tests.utils import PerformanceMeasure

from .utils import CreateJobsForReportMixin


class CSVReportTestCase(CreateJobsForReportMixin):

    def test_csv_download(self):
        self.create_orders_for_report(self.steps, size=16)
        self.client.force_authenticate(self.manager)
        now = timezone.now()
        resp = self.client.get('/api/v2/reports/orders/', {
            'date_from': now - timedelta(weeks=4),
            'date_to': now,
            'driver_id': '',
            'export': 'csv'
        })
        self.assertEqual(resp.status_code, HTTP_200_OK)
        resp = self.client.get('/api/v2/export-reports/{}/'.format(resp.data['id']))
        self.assertEqual(resp.status_code, HTTP_200_OK)
        log_line = resp.data['log'][-1]
        self.assertDictEqual({
            'log': log_line['level'],
            'message': log_line['message'],
            'status': resp.data['status']
        }, {
            'log': 'INFO',
            'message': 'Ready.',
            'status': 'completed'
        })

    @override_settings(BULK_JOB_CREATION_BATCH_SIZE=6, RADARO_CSV={'PANDAS_CHUNKSIZE': 6})
    def test_csv_download_with_small_chunk_size(self):
        self.test_csv_download()

    @tag('performance')
    def test_large_csv_download(self):
        self.client.force_authenticate(self.manager)
        for scale in (50, 100, 250, 100, 50):
            steps = self.get_steps(scale)
            sid = transaction.savepoint()
            self.create_orders_for_report(steps, size=16 * scale)
            measurements = []
            tries = 3
            performance = PerformanceMeasure()
            for ind in xrange(tries):
                now = timezone.now()
                print('\nMeasurement {} with scale: {}\n========================\n'.format(ind + 1, scale), performance)
                resp = self.client.get('/api/v2/reports/orders/', {
                    'date_from': now - timedelta(weeks=4),
                    'date_to': now,
                    'driver_id': '',
                    'export': 'csv'
                })
                self.assertEqual(resp.status_code, HTTP_200_OK)
                resp = self.client.get('/api/v2/export-reports/{}/'.format(resp.data['id']))
                self.assertEqual(resp.status_code, HTTP_200_OK)
                perf, diff = performance.measure()
                print(perf, diff)
                measurements.append(diff)
            print('Average time: {} sec'.format(sum(m.time for m in measurements) / 3.))
            print('Afterall memory growth: {} MB'.format(sum(m.memory for m in measurements)))
            transaction.savepoint_rollback(sid)
