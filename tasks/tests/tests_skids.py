from rest_framework import status
from rest_framework.test import APITestCase

import mock

from base.factories import DriverFactory, ManagerFactory
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory
from tasks.mixins.order_status import OrderStatus
from tasks.models import SKID
from tasks.tests.factories import OrderFactory, SkidFactory


class JobSkidsTestsCase(APITestCase):
    api_url = '/api/v2/orders/'

    @classmethod
    def setUpTestData(cls):
        cls.merchant = MerchantFactory(
            enable_skids=True,
        )
        cls.manager = ManagerFactory(
            merchant=cls.merchant
        )

        cls.job_data = {
            'customer': {
                'name': 'John Sykes'
            },
            'deliver_address': {
                'address': 'Sydney, AU',
                'location': {'lat': 53.907600, 'lng': 27.515333}
            }
        }

    def test_create_job_with_skids(self):
        self.merchant.enable_skids = True
        self.merchant.save()

        cargoes = {
            'skids': [
                {
                    'name': 'Name 1',
                    'quantity': 1,
                    'weight': {'value': 10.0, 'unit': 'kg'},
                    'sizes': {'width': 1.0, 'height': 1.0, 'length': 1.0, 'unit': 'cm'}
                }
            ]
        }
        self.job_data['cargoes'] = cargoes
        self.client.force_authenticate(self.manager)
        response = self.client.post(self.api_url, self.job_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created_cargoes = response.json()['cargoes']
        self.assertEqual(len(cargoes), len(created_cargoes))

    def _create_job_with_skids(self):
        self.merchant.enable_skids = True
        self.merchant.save()
        self.job_with_skids = OrderFactory(
            manager=self.manager,
            merchant=self.merchant,
        )
        self.skids = SkidFactory.create_batch(order=self.job_with_skids, size=3)

    def test_update_skids(self):
        self._create_job_with_skids()
        skid = self.skids[0]
        new_skid_data = {
            'skids': [
                {
                    'id': skid.id,
                    'name': 'Changed name',
                    'quantity': 10,
                    'weight': {'value': 10.0, 'unit': 'kg'},
                    'sizes': {'width': 10.0, 'height': 10.0, 'length': 10.0, 'unit': 'cm'}
                }
            ]
        }
        url = self.api_url + str(self.job_with_skids.id)
        self.client.force_authenticate(self.manager)
        response = self.client.patch(url, {'cargoes': new_skid_data})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        updated_skid = self.job_with_skids.skids.get(id=skid.id)
        self.assertEqual(updated_skid.name, new_skid_data['skids'][0]['name'])
        self.assertEqual(updated_skid.quantity, new_skid_data['skids'][0]['quantity'])
        self.assertEqual(updated_skid.weight, new_skid_data['skids'][0]['weight']['value'])
        self.assertEqual(updated_skid.width, new_skid_data['skids'][0]['sizes']['width'])
        self.assertEqual(updated_skid.height, new_skid_data['skids'][0]['sizes']['height'])
        self.assertEqual(updated_skid.length, new_skid_data['skids'][0]['sizes']['length'])

    def test_add_new_skid_to_existing_job(self):
        self._create_job_with_skids()
        new_skid_data = {
            'skids': [
                {
                    'name': 'Added name',
                    'quantity': 20,
                    'weight': {'value': 20.0, 'unit': 'kg'},
                    'sizes': {'width': 20.0, 'height': 20.0, 'length': 20.0, 'unit': 'cm'}
                }
            ]
        }
        url = self.api_url + str(self.job_with_skids.id)
        skids_num = self.job_with_skids.skids.count()
        self.client.force_authenticate(self.manager)
        response = self.client.patch(url, {'cargoes': new_skid_data})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        current_skids_num = self.job_with_skids.skids.count()
        self.assertEqual(current_skids_num - skids_num, len(new_skid_data['skids']))
        self.assertTrue(self.job_with_skids.skids.filter(name=new_skid_data['skids'][0]['name']).exists())

    def test_remove_skids_from_job(self):
        self._create_job_with_skids()

        skid = self.skids[0]
        skids_to_remove = {
            'skids': [
                {'id': skid.id}
            ]
        }
        url = self.api_url + str(self.job_with_skids.id)
        skids_num = self.job_with_skids.skids.count()
        self.client.force_authenticate(self.manager)
        response = self.client.patch(url, {'cargoes': skids_to_remove})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        current_skids_num = self.job_with_skids.skids.count()
        self.assertEqual(skids_num - current_skids_num, len(skids_to_remove))
        self.assertFalse(self.job_with_skids.skids.filter(id=skid.id))

    def test_create_job_with_disabled_skids(self):
        self.merchant.enable_skids = False
        self.merchant.save()
        cargoes = {
            'skids': [
                {
                    'name': 'Name 1',
                    'quantity': 1,
                    'weight': {'value': 20.0, 'unit': 'kg'},
                    'sizes': {'width': 1.0, 'height': 1.0, 'length': 1.0, 'unit': 'cm'}
                }
            ]
        }
        self.job_data['cargoes'] = cargoes
        self.client.force_authenticate(self.manager)
        response = self.client.post(self.api_url, self.job_data)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class DriverJobSkidsTestsCase(APITestCase):
    skid_detail_url = '/api/v2/orders/{}/skids/{}/'
    skids_url = '/api/v2/orders/{}/skids/'

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

    @mock.patch('webhooks.celery_tasks.send_external_event')
    def test_webhook(self, send_external_event):
        self._create_job_with_skids()
        new_skid_data = {
            'name': 'Added name',
            'weight': {'value': 20.0, 'unit': 'kg'},
            'sizes': {'width': 20.0, 'height': 20.0, 'length': 20.0, 'unit': 'cm'}
        }
        url = self.skids_url.format(self.job_with_skids.id)
        self.client.force_authenticate(self.driver)
        response = self.client.post(url, new_skid_data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        url = '/api/v2/orders/{id}/status/'.format(id=self.job_with_skids.id)
        data = {
            'status': OrderStatus.DELIVERED,
        }
        resp = self.client.put(url, data=data)
        webhook_order_info = send_external_event.call_args[0][1]['order_info']
        self.assertEqual(len(webhook_order_info['cargoes']['skids']), 4)


class SkidsTestsCase(APITestCase):
    order_url = '/api/v2/orders/{}/'
    skid_detail_url = '/api/v2/orders/{}/skids/{}/'
    skids_url = '/api/v2/orders/{}/skids/'

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

    @mock.patch('webhooks.celery_tasks.send_external_event')
    def test_skids_workflow(self, send_external_event):
        self.order = OrderFactory(
            driver=self.driver,
            manager=self.manager,
            merchant=self.merchant,
            status=OrderStatus.IN_PROGRESS,
        )

        manager_cargoes = {
            'skids': [
                {
                    'name': 'Test skid 1',
                    'quantity': 1,
                    'weight': {'value': 10.0, 'unit': 'kg'},
                    'sizes': {'width': 1.0, 'height': 1.0, 'length': 1.0, 'unit': 'cm'}
                }, {
                    'name': 'Test skid 2',
                    'quantity': 1,
                    'weight': {'value': 20.0, 'unit': 'kg'},
                    'sizes': {'width': 2.0, 'height': 2.0, 'length': 2.0, 'unit': 'cm'}
                }, {
                    'name': 'Test skid 3',
                    'quantity': 1,
                    'weight': {'value': 30.0, 'unit': 'kg'},
                    'sizes': {'width': 3.0, 'height': 3.0, 'length': 3.0, 'unit': 'cm'}
                },
            ]
        }
        self.client.force_authenticate(self.manager)
        url = self.order_url.format(self.order.id)
        response = self.client.patch(url, {'cargoes': manager_cargoes})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        skid_ids = [skid['id'] for skid in response.data['cargoes']['skids']]

        result_manager_cargoes = {
            'skids': [
                {
                    'id': skid_ids[0],
                    'name': 'Test skid 1',
                    'quantity': 1,
                    'weight': {'value': 10.0, 'unit': 'kg'},
                    'sizes': {'width': 1.0, 'height': 1.0, 'length': 1.0, 'unit': 'cm'},
                    'driver_changes': None,
                    'original_skid': None,
                }, {
                    'id': skid_ids[1],
                    'name': 'Test skid 2',
                    'quantity': 1,
                    'weight': {'value': 20.0, 'unit': 'kg'},
                    'sizes': {'width': 2.0, 'height': 2.0, 'length': 2.0, 'unit': 'cm'},
                    'driver_changes': None,
                    'original_skid': None,
                }, {
                    'id': skid_ids[2],
                    'name': 'Test skid 3',
                    'quantity': 1,
                    'weight': {'value': 30.0, 'unit': 'kg'},
                    'sizes': {'width': 3.0, 'height': 3.0, 'length': 3.0, 'unit': 'cm'},
                    'driver_changes': None,
                    'original_skid': None,
                },
            ]
        }
        self.assertDictEqual(response.data['cargoes'], result_manager_cargoes)

        self.client.force_authenticate(self.driver)

        new_skid_data = {
            'name': 'Added name',
            'quantity': 40,
            'weight': {'value': 4.0, 'unit': 'kg'},
            'sizes': {'width': 4.0, 'height': 4.0, 'length': 4.0, 'unit': 'cm'}
        }
        url = self.skids_url.format(self.order.id)
        response = self.client.post(url, new_skid_data)
        skid_ids.append(response.data['cargoes']['skids'][3]['id'])

        new_skid_data = {
            'name': 'Update name',
            'quantity': 50,
            'weight': {'value': 5.0, 'unit': 'kg'},
            'sizes': {'width': 5.0, 'height': 5.0, 'length': 5.0, 'unit': 'cm'}
        }
        url = self.skid_detail_url.format(self.order.id, skid_ids[1])
        self.client.put(url, new_skid_data)

        new_skid_data = {
            'name': 'Second update name',
            'quantity': 60,
            'weight': {'value': 6.0, 'unit': 'kg'},
            'sizes': {'width': 6.0, 'height': 6.0, 'length': 6.0, 'unit': 'cm'}
        }
        url = self.skid_detail_url.format(self.order.id, skid_ids[1])
        self.client.put(url, new_skid_data)

        url = self.skid_detail_url.format(self.order.id, skid_ids[2])
        self.client.delete(url, new_skid_data)

        self.client.force_authenticate(self.manager)
        url = self.order_url.format(self.order.id)
        response = self.client.get(url)
        result_manager_cargoes = {
            'skids': [
                {
                    'id': skid_ids[0],
                    'name': 'Test skid 1',
                    'quantity': 1,
                    'weight': {'value': 10.0, 'unit': 'kg'},
                    'sizes': {'width': 1.0, 'height': 1.0, 'length': 1.0, 'unit': 'cm'},
                    'driver_changes': None,
                    'original_skid': None,
                }, {
                    'id': skid_ids[1],
                    'name': 'Second update name',
                    'quantity': 60,
                    'weight': {'value': 6.0, 'unit': 'kg'},
                    'sizes': {'width': 6.0, 'height': 6.0, 'length': 6.0, 'unit': 'cm'},
                    'driver_changes': SKID.EDITED,
                    'original_skid': {
                        'name': 'Test skid 2',
                        'quantity': 1,
                        'weight': {'value': 20.0, 'unit': 'kg'},
                        'sizes': {'width': 2.0, 'height': 2.0, 'length': 2.0, 'unit': 'cm'},
                    },
                }, {
                    'id': skid_ids[2],
                    'name': 'Test skid 3',
                    'quantity': 1,
                    'weight': {'value': 30.0, 'unit': 'kg'},
                    'sizes': {'width': 3.0, 'height': 3.0, 'length': 3.0, 'unit': 'cm'},
                    'driver_changes': SKID.DELETED,
                    'original_skid': {
                        'name': 'Test skid 3',
                        'quantity': 1,
                        'weight': {'value': 30.0, 'unit': 'kg'},
                        'sizes': {'width': 3.0, 'height': 3.0, 'length': 3.0, 'unit': 'cm'},
                    },
                }, {
                    'id': skid_ids[3],
                    'name': 'Added name',
                    'quantity': 40,
                    'weight': {'value': 4.0, 'unit': 'kg'},
                    'sizes': {'width': 4.0, 'height': 4.0, 'length': 4.0, 'unit': 'cm'},
                    'driver_changes': SKID.ADDED,
                    'original_skid': None,
                },
            ]
        }

        self.assertDictEqual(response.data['cargoes'], result_manager_cargoes)

        for skid in result_manager_cargoes['skids']:
            del skid['original_skid']
        del result_manager_cargoes['skids'][2]['name']
        del result_manager_cargoes['skids'][2]['quantity']
        del result_manager_cargoes['skids'][2]['weight']
        del result_manager_cargoes['skids'][2]['sizes']

        self.assertDictEqual(send_external_event.call_args_list[3][0][1]['new_values']['cargoes'], result_manager_cargoes)

        manager_cargoes = {
            'skids': [
                {
                    'id': skid_ids[0],
                    'name': 'Second test skid 1',
                    'quantity': 1,
                    'weight': {'value': 10.0, 'unit': 'kg'},
                    'sizes': {'width': 1.0, 'height': 1.0, 'length': 1.0, 'unit': 'cm'}
                }, {
                    'id': skid_ids[1],
                    'name': 'Second test skid 2',
                    'quantity': 1,
                    'weight': {'value': 20.0, 'unit': 'kg'},
                    'sizes': {'width': 2.0, 'height': 2.0, 'length': 2.0, 'unit': 'cm'}
                }, {
                    'id': skid_ids[2],
                    'name': 'Second test skid 3',
                    'quantity': 1,
                    'weight': {'value': 30.0, 'unit': 'kg'},
                    'sizes': {'width': 3.0, 'height': 3.0, 'length': 3.0, 'unit': 'cm'}
                }, {
                    'id': skid_ids[3],
                }
            ]
        }

        result_manager_cargoes = {
            'skids': [
                {
                    **manager_cargoes['skids'][0],
                    'driver_changes': None,
                    'original_skid': None,
                }, {
                    **manager_cargoes['skids'][1],
                    'driver_changes': None,
                    'original_skid': None,
                }, {
                    **manager_cargoes['skids'][2],
                    'driver_changes': None,
                    'original_skid': None,
                }
            ]
        }

        response = self.client.patch(url, {'cargoes': manager_cargoes})
        self.assertDictEqual(response.data['cargoes'], result_manager_cargoes)
