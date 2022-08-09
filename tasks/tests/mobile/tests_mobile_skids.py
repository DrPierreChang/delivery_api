from rest_framework import status
from rest_framework.test import APITestCase

import mock

from base.factories import DriverFactory, ManagerFactory
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory
from tasks.mixins.order_status import OrderStatus
from tasks.models import SKID
from tasks.tests.factories import OrderFactory, SkidFactory


class DriverJobSkidsTestsCase(APITestCase):
    skid_detail_url = '/api/mobile/orders/v1/{}/skids/{}/'
    skids_url = '/api/mobile/orders/v1/{}/skids/'

    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory(
            enable_skids=True,
        )
        cls.manager = ManagerFactory(
            merchant=cls.merchant
        )
        cls.driver = DriverFactory(
            merchant=cls.merchant,
            work_status=WorkStatus.WORKING,
        )

    def _create_job_with_skids(self):
        self.merchant.enable_skids = True
        self.merchant.save()
        self.driver.work_status = WorkStatus.WORKING
        self.driver.save()
        self.job_with_skids = OrderFactory(
            driver=self.driver,
            manager=self.manager,
            merchant=self.merchant,
            status=OrderStatus.IN_PROGRESS,
        )
        self.skids = SkidFactory.create_batch(order=self.job_with_skids, size=3)

    def test_update_skid_in_wrong_status(self):
        self._create_job_with_skids()
        self.job_with_skids.status = OrderStatus.ASSIGNED
        self.job_with_skids.save()
        skid = self.skids[0]
        new_skid_data = {
            'id': skid.id,
            'name': 'Changed name',
            'weight': {'value': 10.0, 'unit': 'kg'},
            'sizes': {'width': 10.0, 'height': 10.0, 'length': 10.0, 'unit': 'cm'}
        }
        url = self.skid_detail_url.format(self.job_with_skids.id, skid.id)
        self.client.force_authenticate(self.driver)
        response = self.client.put(url, new_skid_data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @mock.patch('webhooks.celery_tasks.send_external_event')
    def test_update_skid(self, send_external_event):
        self._create_job_with_skids()
        skid = self.skids[0]
        new_skid_data = {
            'id': skid.id,
            'name': 'Changed name',
            'weight': {'value': 10.0, 'unit': 'kg'},
            'sizes': {'width': 10.0, 'height': 10.0, 'length': 10.0, 'unit': 'cm'}
        }
        url = self.skid_detail_url.format(self.job_with_skids.id, skid.id)
        self.client.force_authenticate(self.driver)
        response = self.client.put(url, new_skid_data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        updated_skid = self.job_with_skids.skids.get(id=skid.id)
        self.assertEqual(updated_skid.name, new_skid_data['name'])
        self.assertEqual(updated_skid.quantity, 1)
        self.assertEqual(updated_skid.weight, new_skid_data['weight']['value'])
        self.assertEqual(updated_skid.width, new_skid_data['sizes']['width'])
        self.assertEqual(updated_skid.height, new_skid_data['sizes']['height'])
        self.assertEqual(updated_skid.length, new_skid_data['sizes']['length'])
        self.assertEqual(updated_skid.length, new_skid_data['sizes']['length'])
        self.assertEqual(updated_skid.driver_changes, SKID.EDITED)
        self.assertIsNotNone(updated_skid.original_skid)
        self.job_with_skids.refresh_from_db()
        self.assertEqual(self.job_with_skids.changed_in_offline, False)
        self.assertTrue(send_external_event.called)

    @mock.patch('webhooks.celery_tasks.send_external_event')
    def test_add_new_skid(self, send_external_event):
        self._create_job_with_skids()
        new_skid_data = {
            'name': 'Unique added name',
            'weight': {'value': 20.0, 'unit': 'kg'},
            'sizes': {'width': 20.0, 'height': 20.0, 'length': 20.0, 'unit': 'cm'}
        }
        url = self.skids_url.format(self.job_with_skids.id)
        skids_num = self.job_with_skids.skids.count()
        self.client.force_authenticate(self.driver)
        response = self.client.post(url, new_skid_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        current_skids_num = self.job_with_skids.skids.count()
        self.assertEqual(current_skids_num - skids_num, 1)

        added_skid = self.job_with_skids.skids.filter(name=new_skid_data['name']).first()
        self.assertIsNotNone(added_skid)
        self.assertEqual(added_skid.driver_changes, SKID.ADDED)
        self.assertEqual(added_skid.quantity, 1)

        self.assertTrue(send_external_event.called)

    @mock.patch('webhooks.celery_tasks.send_external_event')
    def test_remove_skid(self, send_external_event):
        self._create_job_with_skids()

        url = self.skids_url.format(self.job_with_skids.id)
        self.client.force_authenticate(self.driver)
        response = self.client.get(url)
        skids_num = response.data['count']

        skid = self.skids[0]
        detail_url = self.skid_detail_url.format(self.job_with_skids.id, skid.id)
        self.client.force_authenticate(self.driver)
        response = self.client.delete(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.client.force_authenticate(self.driver)
        response = self.client.get(url)
        current_skids_num = response.data['count']

        self.assertEqual(skids_num - current_skids_num, 1)
        self.assertTrue(send_external_event.called)

        skid.refresh_from_db()
        self.assertIsNotNone(skid.original_skid)

    def test_update_skid_with_disabled_skids(self):
        self._create_job_with_skids()
        self.merchant.enable_skids = False
        self.merchant.save()
        skid = self.skids[0]
        new_skid_data = {
            'id': skid.id,
            'name': 'Changed name',
            'weight': {'value': 10.0, 'unit': 'kg'},
            'sizes': {'width': 10.0, 'height': 10.0, 'length': 10.0, 'unit': 'cm'}
        }
        url = self.skid_detail_url.format(self.job_with_skids.id, skid.id)
        self.client.force_authenticate(self.driver)
        response = self.client.put(url, new_skid_data)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_skid_with_not_working_driver_status(self):
        self._create_job_with_skids()
        self.driver.work_status = WorkStatus.NOT_WORKING
        self.driver.save()
        skid = self.skids[0]
        new_skid_data = {
            'id': skid.id,
            'name': 'Changed name',
            'weight': {'value': 10.0, 'unit': 'kg'},
            'sizes': {'width': 10.0, 'height': 10.0, 'length': 10.0, 'unit': 'cm'}
        }
        url = self.skid_detail_url.format(self.job_with_skids.id, skid.id)
        self.client.force_authenticate(self.driver)
        response = self.client.put(url, new_skid_data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_update_skid_from_offline(self):
        self._create_job_with_skids()
        skid = self.skids[0]
        new_skid_data = {
            'id': skid.id,
            'name': 'Changed name',
            'weight': {'value': 10.0, 'unit': 'kg'},
            'sizes': {'width': 10.0, 'height': 10.0, 'length': 10.0, 'unit': 'cm'},
            'changed_in_offline': True
        }
        url = self.skid_detail_url.format(self.job_with_skids.id, skid.id)
        self.client.force_authenticate(self.driver)
        response = self.client.patch(url, new_skid_data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        updated_skid = self.job_with_skids.skids.get(id=skid.id)
        self.assertEqual(updated_skid.name, new_skid_data['name'])
        self.assertEqual(updated_skid.quantity, 1)
        self.assertEqual(updated_skid.weight, new_skid_data['weight']['value'])
        self.assertEqual(updated_skid.width, new_skid_data['sizes']['width'])
        self.assertEqual(updated_skid.height, new_skid_data['sizes']['height'])
        self.assertEqual(updated_skid.length, new_skid_data['sizes']['length'])
        self.job_with_skids.refresh_from_db()
        self.assertEqual(self.job_with_skids.changed_in_offline, True)

    def test_remove_skid_from_offline(self):
        self._create_job_with_skids()
        self.assertEqual(self.job_with_skids.changed_in_offline, False)
        skid = self.skids[0]
        new_skid_data = {
            'changed_in_offline': True
        }
        url = self.skid_detail_url.format(self.job_with_skids.id, skid.id)
        self.client.force_authenticate(self.driver)
        response = self.client.delete(url, new_skid_data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.job_with_skids.refresh_from_db()
        self.assertEqual(self.job_with_skids.changed_in_offline, True)
