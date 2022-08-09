from datetime import datetime, time, timedelta

from django.test import override_settings
from django.utils import timezone

from rest_framework import status

import mock
import pytz

from base.factories import DriverFactory
from base.models import Member
from base.utils import get_fuzzy_location
from driver.tests.base_test_cases import BaseDriverTestCase
from merchant.factories import LabelFactory, MerchantFactory, SkillSetFactory, SubBrandingFactory
from merchant.models import SubBranding
from notification.factories import FCMDeviceFactory
from tasks.mixins.order_status import OrderStatus
from tasks.models.bulk import OrderPrototype
from tasks.models.orders import Order
from tasks.tests.factories import CustomerFactory, ExternalJobFactory, OrderFactory

from ..factories import MerchantAPIKeyFactory


class BaseMerchantAPIKeyTestCase(BaseDriverTestCase):
    fixtures = ['fixtures/tests/constance.json', ]

    def send_external_job(self, data, status_code=status.HTTP_201_CREATED):
        resp = self.client.post('/api/webhooks/jobs/?key=%s' % self.apikey.key, data=data)
        self.assertEqual(resp.status_code, status_code)
        return resp

    def receive_jobs(self, _id=None, status_code=status.HTTP_200_OK):
        url = '/api/webhooks/jobs/'
        if _id:
            url += '{}/'.format(_id)
        resp = self.client.get(url + '?{}={}'.format('key', self.apikey.key))
        self.assertEqual(resp.status_code, status_code)
        return resp

    def default_payload(self, **kwargs):
        return dict({
            'external_id': 'test-ext-job',
            'customer': {'name': 'new customer'},
            'deliver_address': {'location': get_fuzzy_location()}
        }, **kwargs)

    @classmethod
    def setUpTestData(cls):
        super(BaseMerchantAPIKeyTestCase, cls).setUpTestData()
        Member.objects.filter(id=cls.driver.id).update(first_name='John', last_name='Doe')
        cls.apikey = MerchantAPIKeyFactory(creator=cls.manager, merchant=cls.merchant, available=True)
        cls.ext_job = ExternalJobFactory(source_id=cls.apikey.pk)
        cls.label = LabelFactory(merchant=cls.merchant, color='red')
        cls.subbranding = SubBrandingFactory(merchant=cls.merchant)
        cls.skill_set = SkillSetFactory(merchant=cls.merchant)


class MerchantAPIKeySuccessTestCase(BaseMerchantAPIKeyTestCase):
    def test_get_external_jobs_list(self):
        other_apikey = MerchantAPIKeyFactory(creator=self.manager, merchant=self.merchant, available=True)

        for _ in range(10):
            external_job = ExternalJobFactory(source_id=self.apikey.pk)
            OrderFactory(merchant=self.merchant, external_job=external_job)

        for _ in range(5):
            external_job = ExternalJobFactory(source_id=other_apikey.pk)
            OrderFactory(merchant=self.merchant, external_job=external_job)

        resp = self.client.get('/api/webhooks/jobs/?key=%s' % self.apikey.key,)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], Order.objects.filter(external_job__source_id=self.apikey.pk,
                                                                  merchant=self.merchant).count())
        self.assertNotEqual(resp.data['count'], 0)

    def test_create_external_job_without_driver(self):
        data = self.default_payload()
        self.send_external_job(data)
        order = Order.objects.filter(external_job__external_id=data['external_id']).first()
        self.assertIsNotNone(order)
        self.assertTrue(order.enable_rating_reminder)

    def test_create_external_job_with_disabled_rating_reminder(self):
        data = self.default_payload()
        data['enable_rating_reminder'] = False
        self.send_external_job(data)
        order = Order.objects.filter(external_job__external_id=data['external_id']).first()
        self.assertIsNotNone(order)
        self.assertFalse(order.enable_rating_reminder)

    def test_create_external_job_with_address_2(self):
        data = dict(self.default_payload(), deliver_address_2='123')
        self.send_external_job(data)
        order = Order.objects.filter(external_job__external_id=data['external_id']).first()
        self.assertEqual(order.deliver_address.secondary_address, '123')

    def test_create_external_job_with_pickup_address_2(self):
        pickup_address_data = {'pickup_address': {'location': get_fuzzy_location()}, 'pickup_address_2': '45'}
        data = dict(self.default_payload(), **pickup_address_data)
        self.send_external_job(data)
        order = Order.objects.filter(external_job__external_id=data['external_id']).first()
        self.assertEqual(order.pickup_address.secondary_address, '45')

    def test_create_external_job_with_pickup(self):
        pickup_data = {
            'name': 'IKEA',
            'email': 'ikea@ikea.com',
            'phone': ''
        }
        data = dict(self.default_payload(), pickup=pickup_data)
        self.send_external_job(data, status_code=status.HTTP_400_BAD_REQUEST)
        data.update({'pickup_address': {'location': get_fuzzy_location()}})
        self.send_external_job(data)
        self.assertTrue(Order.objects.filter(external_job__external_id=data['external_id'],
                                             pickup__name=pickup_data['name'],
                                             pickup__email=pickup_data['email'],
                                             pickup__phone=pickup_data['phone'])
                                     .exists())

    def test_create_external_job_with_capacity(self):
        job_capacity = 1500
        data = self.default_payload(capacity=job_capacity)
        self.send_external_job(data, status_code=status.HTTP_400_BAD_REQUEST)
        self.merchant.enable_job_capacity = True
        self.merchant.save()
        self.send_external_job(data)
        self.assertTrue(Order.objects.filter(external_job__external_id=data['external_id'],
                                             capacity=job_capacity).exists())

    def test_create_external_job_with_specified_driver_pk(self):
        data = self.default_payload(driver=self.driver.pk)
        self.send_external_job(data)
        self.assertTrue(Order.objects.filter(external_job__external_id=data['external_id'],
                                             driver=self.driver.pk).exists())

    def test_create_external_job_with_delivery_interval_old_format(self):
        data = self.default_payload()
        delivery_date = (datetime.now() + timedelta(days=1)).date()
        upper_dt, lower_dt = map(
            lambda t: datetime.combine(delivery_date, t, tzinfo=self.merchant.timezone),
            (time(hour=8), time(hour=4))
        )
        upper_str, lower_str = map(lambda dt: dt.astimezone(pytz.UTC).isoformat(), (upper_dt, lower_dt))
        data.update({
            'delivery_interval': {
                'upper': upper_str,
                'lower': lower_str
            }})
        self.send_external_job(data)
        order = Order.objects.filter(external_job__external_id=data['external_id']).first()
        self.assertEqual(order.deliver_after.isoformat(), data['delivery_interval']['lower'])
        self.assertEqual(order.deliver_before.isoformat(), data['delivery_interval']['upper'])

    def test_create_external_job_with_delivery_interval_same_day(self):
        data = self.default_payload()
        delivery_date = (timezone.now() + timedelta(days=1)).date()
        lower_time, upper_time = time(hour=8), time(hour=13, minute=30)

        lower, upper = map(
            lambda t: datetime.combine(delivery_date, t, tzinfo=self.merchant.timezone),
            [lower_time, upper_time]
        )
        lower_str, upper_str = map(lambda dt: dt.astimezone(pytz.UTC).isoformat(), [lower, upper])

        data.update({'deliver_before': upper_str, 'deliver_after': lower_str})
        self.send_external_job(data)
        order = Order.objects.filter(external_job__external_id=data['external_id']).first()
        self.assertEqual(order.deliver_after.isoformat(), lower_str)
        self.assertEqual(order.deliver_before.isoformat(), upper_str)

    def test_create_external_job_with_pickup_interval(self):
        data = self.default_payload()
        pickup_date = (datetime.now() + timedelta(days=1)).date()
        pickup_after_time, pickup_before_time, deliver_before_time = time(hour=13), time(hour=15), time(hour=20)
        pickup_after, pickup_before, deliver_before = map(
            lambda t: datetime.combine(pickup_date, t, tzinfo=self.merchant.timezone),
            (pickup_after_time, pickup_before_time, deliver_before_time))

        pickup_after_str, pickup_before_str, deliver_before_str = map(
            lambda dt: dt.astimezone(pytz.UTC).isoformat(), (pickup_after, pickup_before, deliver_before))

        data.update({'pickup_after': pickup_after_str,
                     'pickup_before': pickup_before_str,
                     'deliver_before': deliver_before_str})
        self.send_external_job(data)
        order = Order.objects.filter(external_job__external_id=data['external_id']).first()

        self.assertEqual(order.pickup_after.isoformat(), pickup_after_str)
        self.assertEqual(order.pickup_before.isoformat(), pickup_before_str)

    def test_create_external_job_with_specified_driver_member_id(self):
        data = self.default_payload(driver=self.driver.member_id)
        self.send_external_job(data)
        self.assertTrue(Order.objects.filter(external_job__external_id=data['external_id'], driver=self.driver.pk).exists())

    def test_create_external_job_only_address(self):
        address = 'Minsk, Belarus'
        data = dict({
            'external_id': 'test-ext-job',
            'customer': {'name': 'new customer'},
            'deliver_address': {'address': address}
        })
        with mock.patch('radaro_utils.geo.AddressGeocoder.geocode') as patched:
            patched.return_value = dict(location='53.9045398,27.5615244', address=address, raw_address=address)
            self.send_external_job(data)
            self.assertTrue(patched.called)
        order_qs = Order.objects.filter(
            external_job__external_id=data['external_id'],
            deliver_address__address=address,
            deliver_address__raw_address=address,
        )
        self.assertTrue(order_qs.exists())

    def test_create_external_job_with_specified_label(self):
        data = self.default_payload(label=self.label.pk)
        self.send_external_job(data)
        self.assertTrue(Order.objects.filter(external_job__external_id=data['external_id'],
                                             labels__id=self.label.pk).exists())

    def test_change_external_job_remove_label(self):
        data = self.default_payload(label=self.label.pk)
        self.send_external_job(data)
        url = '/api/webhooks/jobs/{}?key={}'.format(data['external_id'], self.apikey.key)
        resp = self.client.patch(url, data={'label': None, })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(
            Order.objects.filter(external_job__external_id=data['external_id'], labels__isnull=True).exists())

    def test_change_external_job_change_label(self):
        data = self.default_payload(label=self.label.pk)
        self.send_external_job(data)
        second_label = LabelFactory(merchant=self.merchant, color='green')
        url = '/api/webhooks/jobs/{}?key={}'.format(data['external_id'], self.apikey.key)
        resp = self.client.patch(url, data={'label': second_label.pk, })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(
            Order.objects.filter(external_job__external_id=data['external_id'], labels__id=second_label.pk).exists())

    def test_create_external_job_with_multiple_labels(self):
        self.second_label = LabelFactory(merchant=self.merchant)
        data = self.default_payload(labels=[self.label.pk, self.second_label.pk])
        self.send_external_job(data)
        order = Order.objects.filter(external_job__external_id=data['external_id'],
                                     labels__in=[self.label.pk, self.second_label.pk]).distinct()

        self.assertTrue(order.exists())
        self.assertEqual(order[0].labels.count(), 2)

    def test_change_external_job_remove_labels(self):
        self.second_label = LabelFactory(merchant=self.merchant)
        data = self.default_payload(labels=[self.label.pk, self.second_label.pk])
        self.send_external_job(data)
        url = '/api/webhooks/jobs/{}?key={}'.format(data['external_id'], self.apikey.key)
        resp = self.client.patch(url, data={'labels': [], })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(
            Order.objects.filter(external_job__external_id=data['external_id'], labels__isnull=True).exists())

    def test_create_external_job_with_specified_subbranding(self):
        data = self.default_payload(sub_branding=self.subbranding.pk)
        self.send_external_job(data)
        self.assertTrue(Order.objects.filter(external_job__external_id=data['external_id'],
                                             sub_branding=self.subbranding.pk).exists())

    def test_change_external_job_remove_subbranding(self):
        data = self.default_payload(sub_branding=self.subbranding.pk)
        self.send_external_job(data)
        url = '/api/webhooks/jobs/{}?key={}'.format(data['external_id'], self.apikey.key)
        resp = self.client.patch(url, data={'sub_branding': None, })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(
            Order.objects.filter(external_job__external_id=data['external_id'], sub_branding__isnull=True).exists())

    def test_change_external_job_change_subbranding(self):
        data = self.default_payload(sub_branding=self.subbranding.pk)
        self.send_external_job(data)
        second_subbranding = SubBrandingFactory(merchant=self.merchant)
        url = '/api/webhooks/jobs/{}?key={}'.format(data['external_id'], self.apikey.key)
        resp = self.client.patch(url, data={'sub_branding': second_subbranding.pk, })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(
            Order.objects.filter(external_job__external_id=data['external_id'],
                                 sub_branding=second_subbranding.pk).exists())

    def test_create_external_job_with_skill_set(self):
        skill_sets = [self.skill_set.pk, ]
        data = self.default_payload(skill_sets=skill_sets)
        self.send_external_job(data, status_code=status.HTTP_400_BAD_REQUEST)
        self.driver.skill_sets.add(self.skill_set.pk)
        self.send_external_job(data)
        self.assertTrue(Order.objects.filter(external_job__external_id=data['external_id'],
                                             skill_sets__in=skill_sets).exists())

    def test_change_external_job_remove_skill_set(self):
        self.driver.skill_sets.add(self.skill_set.pk)
        data = self.default_payload(skill_sets=[self.skill_set.pk])
        self.send_external_job(data)
        url = '/api/webhooks/jobs/{}?key={}'.format(data['external_id'], self.apikey.key)
        resp = self.client.patch(url, data={'skill_sets': [], })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        order = Order.objects.get(external_job__external_id=data['external_id'])
        self.assertFalse(order.skill_sets.exists())

    def test_with_used_before_data(self):
        data = self.default_payload()
        data['customer'] = {'phone': '+611900654321', 'email': 'test@au.au', 'name': 'Test Customer'}
        CustomerFactory(merchant=self.merchant, **data['customer'])
        self.send_external_job(data)

    def test_bulk_create_external_jobs(self):
        data = [self.default_payload(**{'external_id': 'test-ext-job-{}'.format(ind)}) for ind in range(1, 3)]
        self.send_external_job(data)
        self.assertEqual(Order.objects.filter(external_job__external_id__icontains='test-ext-job').count(), len(data))

    @override_settings(BULK_JOB_CREATION_BATCH_SIZE=2)
    def test_bulk_create_external_jobs_long_list(self):
        data = [self.default_payload(**{'external_id': 'test-ext-job-{}'.format(ind)}) for ind in range(1, 8)]
        resp = self.send_external_job(data)
        orders = Order.objects.filter(external_job__external_id__icontains='test-ext-job')
        self.assertEqual(orders.count(), len(data))
        prototypes = OrderPrototype.objects.filter(id__in=orders.values('model_prototype'), processed=True, ready=False)
        self.assertEqual(prototypes.count(), len(data))
        self.assertEqual(Order.objects.count(), len(data))

    def test_get_detailed_info_external_job(self):
        OrderFactory(merchant=self.merchant, external_job=self.ext_job)
        resp = self.receive_jobs(_id=self.ext_job.external_id)
        self.assertEqual(resp.data['external_id'], self.ext_job.external_id)
        self.assertTrue('order_confirmation_documents' in resp.data)

    def test_assign_external_job_by_drivers_member_id(self):
        OrderFactory(merchant=self.merchant, external_job=self.ext_job, status=OrderStatus.NOT_ASSIGNED)

        resp = self.client.post('/api/webhooks/jobs/%s/assign/?key=%s' % (self.ext_job.external_id, self.apikey.key),
                                data={'driver': self.driver.member_id, })

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Order.objects.get(external_job__external_id=self.ext_job.external_id).status,
                         OrderStatus.ASSIGNED)

    def test_assign_external_job_by_drivers_pk(self):
        OrderFactory(merchant=self.merchant, external_job=self.ext_job, status=OrderStatus.NOT_ASSIGNED)

        resp = self.client.post('/api/webhooks/jobs/%s/assign/?key=%s' % (self.ext_job.external_id, self.apikey.key),
                                data={'driver': self.driver.pk, })

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Order.objects.get(external_job__external_id=self.ext_job.external_id).status,
                         OrderStatus.ASSIGNED)

    def test_unassign_external_job(self):
        OrderFactory(merchant=self.merchant, external_job=self.ext_job, status=OrderStatus.ASSIGNED, driver=self.driver)

        resp = self.client.post('/api/webhooks/jobs/%s/unassign/?key=%s' % (self.ext_job.external_id, self.apikey.key),
                                data={})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Order.objects.get(external_job__external_id=self.ext_job.external_id).status,
                         OrderStatus.NOT_ASSIGNED)

    def test_failed_external_job(self):
        OrderFactory(merchant=self.merchant, external_job=self.ext_job, status=OrderStatus.ASSIGNED, driver=self.driver)

        resp = self.client.post('/api/webhooks/jobs/%s/terminate/?key=%s' % (self.ext_job.external_id, self.apikey.key),
                                data={})

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(Order.objects.get(external_job__external_id=self.ext_job.external_id).status,
                         OrderStatus.FAILED)

    def test_get_drivers_list(self):
        resp = self.client.get('/api/webhooks/drivers/?key=%s' % self.apikey.key)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], Member.drivers.filter(merchant=self.apikey.merchant).count())
        self.assertNotEqual(resp.data['count'], 0)

    def test_get_detailed_driver_info_by_pk(self):
        resp = self.client.get('/api/webhooks/drivers/%s/?key=%s' % (self.driver.id, self.apikey.key))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['member_id'], self.driver.member_id)

    def test_get_detailed_driver_info_by_member_id(self):
        resp = self.client.get('/api/webhooks/drivers/%s/?key=%s' % (self.driver.member_id, self.apikey.key))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['member_id'], self.driver.member_id)

    def test_get_subbrands_list(self):
        other_merchant = MerchantFactory()
        SubBrandingFactory.create_batch(size=5, merchant=self.merchant)
        SubBrandingFactory.create_batch(size=2, merchant=other_merchant)

        resp = self.client.get('/api/webhooks/sub-brands/?key=%s' % self.apikey.key)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], SubBranding.objects.filter(merchant=self.merchant).count())

    def test_get_detailed_subbrand_info(self):
        subbranding = SubBrandingFactory(merchant=self.merchant, name='My Brand')
        resp = self.client.get('/api/webhooks/sub-brands/%s/?key=%s' % (subbranding.id, self.apikey.key))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['name'], subbranding.name)

    def test_change_external_job_skid_workflow(self):
        self.merchant.enable_skids = False
        self.merchant.save()
        cargoes = {
            'skids': [{
                'name': 'Trying to create with disalbed skids',
                'quantity': 10,
                'weight': {
                    'value': 10.0,
                    'unit': 'kg'
                },
                'sizes': {
                    'unit': 'cm',
                    'width': 10.0,
                    'height': 10.0,
                    'length': 10.0
                }
            }]
        }
        data = dict(self.default_payload(), cargoes=cargoes)
        self.send_external_job(data, status_code=status.HTTP_400_BAD_REQUEST)

        # Create order with skid
        self.merchant.enable_skids = True
        self.merchant.save()
        cargoes = {
            'skids': [{
                'name': 'Created with jobs',
                'quantity': 1,
                'weight': {
                    'value': 1.0,
                    'unit': 'kg'
                },
                'sizes': {
                    'unit': 'cm',
                    'width': 1.0,
                    'height': 1.0,
                    'length': 1.0
                }
            }]
        }
        data = dict(self.default_payload(), cargoes=cargoes)
        self.send_external_job(data)
        order = Order.objects.filter(external_job__external_id=data['external_id']).first()
        self.assertEqual(order.skids.count(), 1)
        skid = order.skids.first()
        self.assertEqual(skid.name, cargoes['skids'][0]['name'])
        self.assertEqual(skid.quantity, cargoes['skids'][0]['quantity'])

        # Change skid
        url = '/api/webhooks/jobs/{}?key={}'.format(data['external_id'], self.apikey.key)
        cargoes = {
            'skids': [{
                'id': skid.id,
                'name': 'Changed existing skid',
                'quantity': 2,
                'weight': {
                    'value': 2.0,
                    'unit': 'lb'
                },
                'sizes': {
                    'unit': 'cm',
                    'width': 2.0,
                    'height': 2.0,
                    'length': 2.0
                }
            }]
        }
        resp = self.client.patch(url, data={'cargoes': cargoes, })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.skids.count(), 1)
        skid = order.skids.first()
        self.assertEqual(skid.name, cargoes['skids'][0]['name'])
        self.assertEqual(skid.quantity, cargoes['skids'][0]['quantity'])

        # Delete skid
        url = '/api/webhooks/jobs/{}?key={}'.format(data['external_id'], self.apikey.key)
        cargoes = {
            'skids': [{
                'id': skid.id,
            }]
        }
        resp = self.client.patch(url, data={'cargoes': cargoes, })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.skids.count(), 0)

        # Add skid
        url = '/api/webhooks/jobs/{}?key={}'.format(data['external_id'], self.apikey.key)
        cargoes = {
            'skids': [{
                'name': 'Added new skid',
                'quantity': 4,
                'weight': {
                    'value': 4.0,
                    'unit': 'kg'
                },
                'sizes': {
                    'unit': 'in',
                    'width': 4.0,
                    'height': 4.0,
                    'length': 4.0
                }
            }]
        }
        resp = self.client.patch(url, data={'cargoes': cargoes, })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.skids.count(), 1)
        skid = order.skids.first()
        self.assertEqual(skid.name, cargoes['skids'][0]['name'])
        self.assertEqual(skid.quantity, cargoes['skids'][0]['quantity'])

        # Add skid in other status
        url = '/api/webhooks/jobs/{}?key={}'.format(data['external_id'], self.apikey.key)
        cargoes = {
            'skids': [{
                'name': 'Added new skid in other status',
                'quantity': 5,
                'weight': {
                    'value': 5.0,
                    'unit': 'kg'
                },
                'sizes': {
                    'unit': 'cm',
                    'width': 5.0,
                    'height': 5.0,
                    'length': 5.0
                }
            }]
        }
        order.driver = self.driver
        order.status = OrderStatus.IN_PROGRESS
        order.save()
        FCMDeviceFactory(user=self.driver)

        with mock.patch('notification.celery_tasks.send_device_notification.delay') as send_notification:
            resp = self.client.patch(url, data={'cargoes': cargoes, })
            self.assertTrue(send_notification.called)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        order.refresh_from_db()
        self.assertEqual(order.skids.count(), 2)

        # Add skid in forbidden status
        url = '/api/webhooks/jobs/{}?key={}'.format(data['external_id'], self.apikey.key)
        cargoes = {
            'skids': [{
                'name': 'Add skid in forbidden status',
                'quantity': 6,
                'weight': {
                    'value': 6.0,
                    'unit': 'kg'
                },
                'sizes': {
                    'unit': 'cm',
                    'width': 6.0,
                    'height': 6.0,
                    'length': 6.0
                }
            }]
        }
        order.status = OrderStatus.WAY_BACK
        order.save()
        resp = self.client.patch(url, data={'cargoes': cargoes, })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class MerchantAPIKeyErrorTestCase(BaseMerchantAPIKeyTestCase):
    def setUp(self):
        self.data = {
            'external_id': 'test-ext-job-1',
            'customer': {'name': 'new customer'},
            'deliver_address': {'location': get_fuzzy_location()},
            'status': Order.IN_PROGRESS,
            'driver': self.driver.member_id
        }

    def test_create_external_job_with_in_progress_status_and_driver(self):
        resp = self.client.post('/api/webhooks/jobs/?key=%s' % self.apikey.key, data=self.data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_external_job_with_delivered_status_and_driver(self):
        self.data['status'] = OrderStatus.DELIVERED
        resp = self.client.post('/api/webhooks/jobs/?key=%s' % self.apikey.key, data=self.data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_external_job_with_confirmed_status_and_driver(self):
        self.data.update({
            'status': Order.DELIVERED,
            'is_confirmed_by_customer': True
        })
        resp = self.client.post('/api/webhooks/jobs/?key=%s' % self.apikey.key, data=self.data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_external_job_with_specified_drivers_name(self):
        self.data.update({
            'status': Order.ASSIGNED,
            'driver': self.driver.get_full_name()
        })
        resp = self.client.post('/api/webhooks/jobs/?key=%s' % self.apikey.key, data=self.data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_external_job_with_failed_status_and_driver(self):
        self.data['status'] = OrderStatus.FAILED
        resp = self.client.post('/api/webhooks/jobs/?key=%s' % self.apikey.key, data=self.data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_assign_external_job_by_not_own_driver(self):
        OrderFactory(merchant=self.merchant, external_job=self.ext_job, status=OrderStatus.NOT_ASSIGNED)
        other_driver = DriverFactory(merchant=MerchantFactory())

        resp = self.client.post('/api/webhooks/jobs/%s/assign/?key=%s' % (self.ext_job.external_id, self.apikey.key),
                                data={'driver': other_driver.pk, })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_external_job_without_external_id(self):
        del self.data['external_id']
        resp = self.client.post('/api/webhooks/jobs/?key=%s' % (self.apikey.key,),
                                data=self.data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual({'external_id', 'passed_external_id', 'status'}, set(resp.data['errors'][0].keys()))

    def test_create_external_job_with_other_merchants_label(self):
        other_merchant = MerchantFactory()
        other_label = LabelFactory(merchant=other_merchant)
        data = self.default_payload(label=other_label.pk)
        resp = self.send_external_job(data, status_code=status.HTTP_400_BAD_REQUEST)
        self.assertContains(resp, "This is not merchant's label", status_code=status.HTTP_400_BAD_REQUEST)

    def test_create_external_job_with_not_existed_specified_label(self):
        data = self.default_payload(label=0)
        resp = self.send_external_job(data, status_code=status.HTTP_400_BAD_REQUEST)
        self.assertDictEqual({
            'errors': [{
                'passed_external_id': u'test-ext-job',
                'label': [u'Invalid pk "0" - object does not exist.'],
            }, ],
            "detail": 'Invalid pk "0" - object does not exist.'
        }, resp.json())

    def test_create_external_job_with_other_merchants_subbranding(self):
        other_merchant = MerchantFactory()
        other_subbranding = SubBrandingFactory(merchant=other_merchant)
        data = self.default_payload(sub_branding=other_subbranding.pk)
        resp = self.send_external_job(data, status_code=status.HTTP_400_BAD_REQUEST)
        self.assertContains(resp, "This is not merchant's sub_branding", status_code=status.HTTP_400_BAD_REQUEST)

    def test_create_external_job_with_not_existed_specified_subbranding(self):
        data = self.default_payload(sub_branding=0)
        resp = self.send_external_job(data, status_code=status.HTTP_400_BAD_REQUEST)
        self.assertDictEqual({
            'errors': [{
                'passed_external_id': u'test-ext-job',
                'sub_branding': [u'Invalid pk "0" - object does not exist.'],
            },],
            "detail": 'Invalid pk "0" - object does not exist.'
        }, resp.json())

    def test_create_external_job_without_address_location(self):
        data = dict({
            'external_id': 'test-ext-job',
            'customer': {'name': 'new customer'},
            'deliver_address': {}
        })
        self.send_external_job(data, status_code=status.HTTP_400_BAD_REQUEST)

    def test_create_external_job_address_not_found(self):
        address = 'Minsk, Belarus'
        data = dict({
            'external_id': 'test-ext-job',
            'customer': {'name': 'new customer'},
            'deliver_address': {'address': address}
        })
        with mock.patch('radaro_utils.geo.AddressGeocoder.geocode') as patched:
            patched.return_value = None
            self.send_external_job(data, status_code=status.HTTP_400_BAD_REQUEST)
            self.assertTrue(patched.called)

    def test_assign_job_with_high_capacity(self):
        self.merchant.enable_job_capacity = True
        self.merchant.save()
        self.driver.car.capacity = 200
        self.driver.car.save()

        data = self.default_payload(capacity=1500)
        self.send_external_job(data)

        url = '/api/webhooks/jobs/{}?key={}'.format(data['external_id'], self.apikey.key)
        resp = self.client.patch(url, data={'driver': self.driver.id, 'status': OrderStatus.ASSIGNED})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @override_settings(BULK_JOB_CREATION_BATCH_SIZE=2)
    def test_bulk_upload_with_errors(self):
        data = [self.default_payload(**{'external_id': 'test-ext-job-{}'.format(ind)}) for ind in range(1, 7)]
        data[2]['sub_branding'] = 123
        resp = self.send_external_job(data, status_code=status.HTTP_400_BAD_REQUEST)
        self.assertDictEqual({
            'errors': [{}, {}, {
                'passed_external_id': u'test-ext-job-3',
                'sub_branding': [u'Invalid pk "123" - object does not exist.'],
            }, {}] + [{}] * 2,
            "detail": 'Invalid pk "123" - object does not exist.'
        }, resp.json())
        self.assertEqual(Order.objects.filter(external_job__external_id__icontains='test-ext-job').count(), 0)

    @override_settings(BULK_JOB_CREATION_BATCH_SIZE=2)
    def test_bulk_upload_with_non_unique_external_ids(self):
        data = [self.default_payload(**{'external_id': 'test-ext-job-{}'.format(ind // 2)}) for ind in range(2, 6)]
        resp = self.send_external_job(data, status_code=status.HTTP_400_BAD_REQUEST)
        self.assertDictEqual({
            'errors': {
                'non_field_errors': [u'External id test-ext-job-1 in orders list is not unique.']
            },
            'detail': 'External id test-ext-job-1 in orders list is not unique.'
        }, resp.json())
        data = [self.default_payload(**{'external_id': 'test-ext-job-{}'.format(ind % 2)}) for ind in range(1, 5)]
        resp = self.send_external_job(data, status_code=status.HTTP_400_BAD_REQUEST)
        self.assertDictEqual({
            'errors': {
                'non_field_errors': [u'External id test-ext-job-1 in orders list is not unique.']
            },
            'detail': 'External id test-ext-job-1 in orders list is not unique.'
        }, resp.json())
        self.assertEqual(Order.objects.filter(external_job__external_id__icontains='test-ext-job').count(), 0)

    @override_settings(BULK_JOB_CREATION_BATCH_SIZE=2)
    def test_bulk_upload_already_existing(self):
        data = [self.default_payload(**{'external_id': 'test-ext-job-{}'.format(ind % 2)}) for ind in range(1, 5)]
        resp = self.send_external_job(data[:2], status_code=status.HTTP_201_CREATED)
        resp = self.send_external_job(data[2:], status_code=status.HTTP_400_BAD_REQUEST)
        expected = {
            'errors': [
                {
                    'non_field_errors': [
                        'Order with such api key and id "test-ext-job-1" already exists.'
                    ],
                    'passed_external_id': 'test-ext-job-1'
                },
                {
                    'non_field_errors': [
                        'Order with such api key and id "test-ext-job-0" already exists.'
                    ],
                    'passed_external_id': 'test-ext-job-0'
                }
            ],
            'detail': 'Order with such api key and id "test-ext-job-1" already exists.'
        }
        self.assertDictEqual(expected, resp.json())
        self.assertEqual(Order.objects.count(), 2)

    def test_create_external_job_with_zero_coordinate(self):
        data = self.default_payload(driver=self.driver.pk)
        address = 'Minsk zero, Belarus'
        location = '6.11111,6.11111'
        data['deliver_address'] = {
            'location': '0.000,0.00',
            'address': address,
        }
        with mock.patch('radaro_utils.geo.AddressGeocoder.geocode') as patched:
            patched.return_value = dict(location=location, address=address, raw_address='')
            self.send_external_job(data)
            self.assertTrue(patched.called)
        order_qs = Order.objects.filter(
            external_job__external_id=data['external_id'],
            deliver_address__location=location,
            deliver_address__address=address,
            deliver_address__raw_address='',
        )
        self.assertTrue(order_qs.exists())

    def test_create_external_job_with_zero_coordinate_without_address(self):
        data = self.default_payload(driver=self.driver.pk)
        data['deliver_address']['location'] = '0.000,0.00'
        self.send_external_job(data, status_code=status.HTTP_400_BAD_REQUEST)

    def test_async_order_processing(self):
        order = OrderFactory(merchant=self.merchant, external_job=self.ext_job,
                             driver=self.driver, status=OrderStatus.IN_PROGRESS)

        self.client.force_authenticate(self.driver)
        self.client.put('/api/v2/orders/{}/geofence'.format(order.id), data={'geofence_entered': True})
        with mock.patch('webhooks.celery_tasks.send_external_event') as send_external_event:
            self.client.put('/api/v2/orders/{}/status'.format(order.id), data={'status': OrderStatus.DELIVERED})
            order.refresh_from_db()
            self.assertIsNotNone(order.time_at_job)
            webhook_data = send_external_event.call_args[0][1]
            self.assertIsNotNone(webhook_data['order_info']['duration'])

    @mock.patch('webhooks.celery_tasks.send_external_event')
    def test_send_order_creation_webhook(self, send_external_event):
        self.send_external_job(self.default_payload())
        self.assertTrue(send_external_event.called)
