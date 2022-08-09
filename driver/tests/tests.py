from __future__ import unicode_literals

from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from rest_framework import status
from rest_framework.status import HTTP_200_OK

from factory.fuzzy import FuzzyChoice
from mock import patch

from base.factories import DriverFactory, DriverLocationFactory
from base.models import Member
from driver.tests.base_test_cases import BaseDriverTestCase
from driver.utils import DriverStatus, WorkStatus
from merchant.factories import MerchantFactory, SkillSetFactory
from notification.factories import FCMDeviceFactory
from reporting.models import Event
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order
from tasks.tests.factories import OrderFactory

MERCHANT_DRIVERS_AMOUNT = 20
ANOTHER_MERCHANT_DRIVERS_AMOUNT = 10


class DriverTestCase(BaseDriverTestCase):
    @classmethod
    def setUpTestData(cls):
        super(DriverTestCase, cls).setUpTestData()
        cls.merchant.enable_skill_sets = True
        cls.merchant.save(update_fields=['enable_skill_sets'])
        for merchant, amount in ((cls.merchant, MERCHANT_DRIVERS_AMOUNT),
                                 (MerchantFactory(), ANOTHER_MERCHANT_DRIVERS_AMOUNT)):
            DriverFactory.create_batch(
                size=amount - 3,
                merchant=merchant,
                work_status=FuzzyChoice([WorkStatus.NOT_WORKING, WorkStatus.WORKING, WorkStatus.ON_BREAK]).fuzz(),
                has_internet_connection=True,
            )
            DriverFactory.create_batch(
                size=2,
                merchant=merchant,
                work_status=WorkStatus.WORKING,
                has_internet_connection=True,
            )
        cls.skill_set = SkillSetFactory(merchant=cls.merchant)
        cls.secret_skill_set = SkillSetFactory(merchant=cls.merchant, is_secret=True)
        cls.driver.work_status = WorkStatus.WORKING
        cls.driver.save()

    @patch('notification.celery_tasks.send_device_notification.delay')
    def test_driver_offline_status(self, send_notification):
        self.client.force_authenticate(self.manager)
        driver = Member.objects.filter(
            merchant=self.merchant,
            role=Member.DRIVER,
            work_status=WorkStatus.WORKING
        ).first()
        driver.has_internet_connection = True
        driver.save()
        FCMDeviceFactory(user=driver)
        resp = self.client.put('/api/drivers/%s/status/' % driver.id, {
            'is_online': False,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertDictEqual(send_notification.call_args[1]['message'], {
            "data": {
                "text": '{}, you have been forced offline by the manager {}'.format(driver.first_name,
                                                                                self.manager.full_name),
                "update": {'is_online': False, 'work_status': WorkStatus.NOT_WORKING}
            },
            "type": "FORCED_UPDATE_BY_MANAGER"
        })
        self.assertFalse(Member.drivers.get(id=driver.id).is_online)

    @patch('notification.celery_tasks.send_device_notification.delay')
    def test_driver_not_working_status(self, send_notification):
        self.client.force_authenticate(self.manager)
        driver = Member.objects.filter(
            merchant=self.merchant,
            role=Member.DRIVER,
            work_status=WorkStatus.WORKING,
        ).first()
        driver.has_internet_connection = True
        driver.save()
        FCMDeviceFactory(user=driver)
        resp = self.client.put('/api/drivers/%s/status/' % driver.id, {
            'work_status': WorkStatus.NOT_WORKING,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertDictEqual(send_notification.call_args[1]['message'], {
            "data": {
                "text": '{}, you have been forced offline by the manager {}'.format(driver.first_name,
                                                                                self.manager.full_name),
                "update": {'is_online': False, 'work_status': WorkStatus.NOT_WORKING}
            },
            "type": "FORCED_UPDATE_BY_MANAGER"
        })
        self.assertFalse(Member.drivers.get(id=driver.id).is_online)

    def test_get_online_drivers(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/drivers/online/', {})
        self.assertEqual(
            resp.data['count'],
            Member.drivers.filter(merchant=self.merchant, work_status=WorkStatus.WORKING).count()
        )

    def test_filter_drivers_by_ids(self):
        self.client.force_authenticate(self.manager)
        all_drivers = Member.drivers.filter(merchant=self.merchant)
        resp = self.client.get('/api/drivers/', {'id': list(all_drivers.values_list('id', flat=True))})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], all_drivers.count())

    def test_after_logout_driver_has_offline_event(self):
        loc = DriverLocationFactory(member=self.driver)
        self.driver.last_location = loc
        self.driver.work_status = WorkStatus.WORKING
        self.driver.save()
        self.client.force_authenticate(self.driver)
        resp = self.client.delete('/api/auth/logout/')
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(Event.objects.filter(initiator=self.driver).count(), 2)
        self.assertEqual(
            Event.objects.filter(initiator=self.driver, field='work_status').first().obj_dump,
            {'last_location': {'location': loc.location}},
        )

    def test_after_logout_driver_has_offline_event_without_location(self):
        self.driver.last_location = None
        self.driver.work_status = WorkStatus.WORKING
        self.driver.save()
        self.client.force_authenticate(self.driver)
        resp = self.client.delete('/api/auth/logout/')
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(Event.objects.filter(initiator=self.driver).count(), 2)
        self.assertEqual(Event.objects.filter(initiator=self.driver, field='work_status').first().obj_dump, None)

    def test_status_count(self):
        self.merchant.use_way_back_status = True
        self.merchant.save()
        # Set one driver status NOT_WORKING
        offline_driver = Member.drivers.filter(merchant=self.merchant).first()
        offline_driver.work_status = WorkStatus.NOT_WORKING
        offline_driver.save()
        # Other drivers get status ASSIGNED
        Member.drivers.exclude(id=offline_driver.id).update(work_status=WorkStatus.WORKING)
        for driver in Member.drivers.filter(merchant=self.merchant):
            OrderFactory(
                merchant=self.merchant,
                manager=self.manager,
                driver=driver,
                status=OrderStatus.ASSIGNED
            )
        # Update some drivers to get specific statuses
        statuses = (OrderStatus._status[0], ) + OrderStatus._status[-6:]
        drivers = Member.drivers.filter(merchant=self.merchant).exclude(id=offline_driver.id)[:len(statuses)]
        for ind, driver in enumerate(drivers):
            status = statuses[ind][0]
            driver.order_set.all().update(status=status)
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/v2/drivers/count_items')
        self.assertEqual(resp.status_code, HTTP_200_OK)
        count_dict = {
            DriverStatus.UNASSIGNED: 3,
            DriverStatus.PICK_UP: 1,
            DriverStatus.PICKED_UP: 1,
            DriverStatus.IN_PROGRESS: 1,
            DriverStatus.WAY_BACK: 1,
            WorkStatus.WORKING: 19,
            WorkStatus.NOT_WORKING: 1,
            WorkStatus.ON_BREAK: 0,
        }
        count_dict[DriverStatus.ASSIGNED] = MERCHANT_DRIVERS_AMOUNT - sum(list(count_dict.values())[:-3])
        self.assertDictEqual(resp.data, count_dict)

    def test_status_count_with_forced_offline(self):
        Member.drivers.update(work_status=WorkStatus.WORKING, is_offline_forced=False)
        offline_driver = Member.drivers.filter(merchant=self.merchant).first()
        offline_driver.work_status = WorkStatus.WORKING
        offline_driver.is_offline_forced = True
        offline_driver.save()

        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/v2/drivers/count_items')
        self.assertEqual(resp.status_code, HTTP_200_OK)
        self.assertEqual(resp.data['not_working'], 1)

    def test_getting_driver_list_with_deleted_orders(self):
        def count_drivers():
            resp = self.client.get('/api/drivers/')
            self.assertEqual(resp.status_code, HTTP_200_OK)
            self.assertEqual(resp.data['count'], Member.drivers.filter(merchant=self.merchant).count())

        orders = OrderFactory.create_batch(
            size=2,
            status=OrderStatus.ASSIGNED,
            driver=self.driver,
            merchant=self.merchant
        )
        self.client.force_authenticate(self.manager)
        count_drivers()
        Order.objects.filter(id__in=(o.id for o in orders)).update(deleted=True)
        count_drivers()

    def test_driver_status(self):
        orders = OrderFactory.create_batch(
            size=2,
            status=OrderStatus.ASSIGNED,
            driver=self.driver,
            merchant=self.merchant
        )
        self.client.force_authenticate(self.manager)
        self.driver.work_status = WorkStatus.WORKING
        self.driver.save()
        self.assertEqual(Member.drivers_with_statuses.get(id=self.driver.id).status, self.driver.status)
        Order.objects.filter(id__in=(o.id for o in orders)).update(deleted=True)
        self.assertEqual(Member.drivers_with_statuses.get(id=self.driver.id).status, self.driver.status)
        self.assertEqual(self.driver.status, DriverStatus.UNASSIGNED)

    def test_skill_sets_adding(self):
        self.client.force_authenticate(self.driver)
        url = '/api/drivers/{}/skill-sets/'

        skill_sets = {
            "skill_sets": [self.skill_set.id]
        }
        resp = self.client.post(url.format(self.driver.id), skill_sets)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(resp.json()), len(skill_sets["skill_sets"]))

    def test_secret_skill_sets_adding(self):
        self.client.force_authenticate(self.driver)
        url = '/api/drivers/{}/skill-sets/'

        skill_sets = {
            "skill_sets": [self.secret_skill_set.id]
        }
        resp = self.client.post(url.format(self.driver.id), skill_sets)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_skill_sets_deletion(self):
        self.client.force_authenticate(self.driver)
        url = '/api/drivers/{}/skill-sets/'
        self.driver.skill_sets.add(self.skill_set)
        self.assertTrue(self.driver.skill_sets.exists())

        skill_sets = {
            "skill_sets": [self.skill_set.id]
        }
        resp = self.client.delete(url.format(self.driver.id), skill_sets)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(self.driver.skill_sets.exists())

    def test_secret_skill_sets_deletion(self):
        self.client.force_authenticate(self.driver)
        url = '/api/drivers/{}/skill-sets/'

        skill_sets = {
            "skill_sets": [self.secret_skill_set.id]
        }
        resp = self.client.delete(url.format(self.driver.id), skill_sets)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_skill_sets_deletion_with_active_jobs(self):
        self.client.force_authenticate(self.driver)
        self.driver.skill_sets.add(self.skill_set)
        order = OrderFactory(
                merchant=self.merchant,
                manager=self.manager,
                driver=self.driver,
                status=OrderStatus.IN_PROGRESS
            )
        order.skill_sets.add(self.skill_set)

        url = '/api/drivers/{}/skill-sets/'
        skill_sets = {
            "skill_sets": [self.skill_set.id]
        }

        resp = self.client.delete(url.format(self.driver.id), skill_sets)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('notification.celery_tasks.send_device_notification.delay')
    def test_skill_sets_deletion_with_assigned_jobs(self, send_notification):
        self.client.force_authenticate(self.driver)
        FCMDeviceFactory(user=self.driver)
        self.driver.skill_sets.add(self.skill_set)
        order = OrderFactory(
                merchant=self.merchant,
                manager=self.manager,
                driver=self.driver,
                status=OrderStatus.ASSIGNED
            )
        order.skill_sets.add(self.skill_set)

        url = '/api/drivers/{pk}/skill-sets/?{query}'
        skill_sets = {
            "skill_sets": [self.skill_set.id]
        }

        resp = self.client.delete(url.format(pk=self.driver.id, query=''), skill_sets)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        resp = self.client.delete(url.format(pk=self.driver.id, query='force'), skill_sets)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        order.refresh_from_db()
        self.assertIsNone(order.driver)

        send_notification.assert_called()
        self.assertTrue(send_notification.call_args[1]['content_available'])

    def test_locations_in_change_status_events(self):
        driver = DriverFactory(
                merchant=self.merchant,
                work_status=WorkStatus.WORKING
            )
        loc = DriverLocationFactory(member=driver)
        driver.last_location = loc
        driver.save()
        self.client.force_authenticate(driver)

        self.client.put('/api/drivers/me/status/', {
            'is_online': False,
        })
        self.client.put('/api/drivers/me/status/', {
            'offline_happened_at': timezone.now().timestamp(),
            'is_online': True,
            'location': {'location': {'lat': 53.907600, 'lng': 27.515333}}
        })
        self.client.put('/api/drivers/me/status/', {
            'offline_happened_at': timezone.now().timestamp(),
            'work_status': WorkStatus.NOT_WORKING,
        })

        events = driver.events.all().filter(event=Event.CHANGED, field='work_status')
        events = list(events.order_by('happened_at'))

        self.assertEqual(len(events), 3)
        self.assertTrue(events[0].obj_dump and 'last_location' in events[0].obj_dump)
        self.assertTrue(events[1].obj_dump and 'last_location' in events[1].obj_dump)
        self.assertTrue(events[2].obj_dump is None)

        resp = self.client.put('/api/drivers/me/status/', {
            'offline_happened_at': (timezone.now() - timedelta(days=1)).timestamp(),
            'work_status': WorkStatus.NOT_WORKING,
        })
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('notification.celery_tasks.send_device_notification.delay')
    def test_forced_offline(self, send_notification):
        driver = DriverFactory(
            merchant=self.merchant,
            work_status=WorkStatus.WORKING
        )
        driver.work_status = WorkStatus.WORKING
        driver.has_internet_connection = True
        driver.save()
        FCMDeviceFactory(user=driver)

        self.client.force_authenticate(self.manager)

        # not working

        res = self.client.put('/api/v2/drivers/{}/status/'.format(driver.id), {
            'work_status': WorkStatus.NOT_WORKING,
        })
        res = self.client.get('/api/v2/drivers/{}/'.format(driver.id))
        driver.refresh_from_db()
        self.assertEqual(driver.work_status, WorkStatus.NOT_WORKING)
        self.assertEqual(driver.is_online, False)
        self.assertEqual(res.data['work_status'], WorkStatus.NOT_WORKING)
        self.assertEqual(res.data['is_online'], False)

        driver.work_status = WorkStatus.WORKING
        driver.has_internet_connection = False
        driver.save()

        # virtual not working for manager

        res = self.client.put('/api/v2/drivers/{}/status/'.format(driver.id), {
            'work_status': WorkStatus.NOT_WORKING,
        })
        driver.refresh_from_db()
        self.assertEqual(driver.work_status, WorkStatus.WORKING)
        self.assertEqual(driver.is_online, True)

        res = self.client.get('/api/v2/drivers/{}/'.format(driver.id))
        self.assertEqual(res.data['work_status'], WorkStatus.NOT_WORKING)
        self.assertEqual(res.data['is_online'], False)
        res = self.client.get('/api/v2/drivers/{}/status/'.format(driver.id))
        self.assertEqual(res.data['work_status'], WorkStatus.NOT_WORKING)
        self.assertEqual(res.data['is_online'], False)
        self.assertEqual(driver.get_manager_who_offline_driver().id, self.manager.id)

        self.client.force_authenticate(driver)

        res = self.client.get('/api/v2/drivers/{}/status/'.format(driver.id))
        self.assertEqual(res.data['work_status'], WorkStatus.WORKING)
        self.assertEqual(res.data['is_online'], True)

        # this api additionally makes ping
        self.client.post('/api/drivers/me/locations/', [{
            'location': '53.907600,27.515333', 'timestamp': timezone.now().timestamp()
        }])
        driver.refresh_from_db()

        res = self.client.get('/api/v2/drivers/{}/'.format(driver.id))
        self.assertEqual(res.data['work_status'], WorkStatus.NOT_WORKING)
        self.assertEqual(res.data['is_online'], False)

        self.assertEqual(len(send_notification.call_args_list), 2)

        driver_ct = ContentType.objects.get_for_model(Member)
        events = Event.objects.filter(object_id=driver.id, content_type=driver_ct, event=Event.CHANGED)
        event = events.filter(field='work_status').order_by('-created_at').first()
        self.assertEqual(self.manager.id, event.initiator.id)

    def test_bulk_change_status(self):
        driver = DriverFactory(
            merchant=self.merchant,
            work_status=WorkStatus.WORKING
        )
        driver.work_status = WorkStatus.WORKING
        driver.has_internet_connection = False
        driver.save()
        self.client.force_authenticate(driver)
        timestamp = timezone.now().timestamp()
        resp = self.client.put(
            '/api/v2/drivers/{}/status/'.format(driver.id),
            [{
                'offline_happened_at': timestamp - 100,
                'work_status': WorkStatus.ON_BREAK,
                'location': {
                    'location': {
                        'lat': 53.907600,
                        'lng': 27.515333,
                    }
                }
            }, {
                'offline_happened_at': timestamp - 90,
                'work_status': WorkStatus.NOT_WORKING,
                'location': {
                    'location': {
                        'lat': 53.907600,
                        'lng': 27.515333,
                    }
                }
            }, {
                'offline_happened_at': timestamp - 80,
                'work_status': WorkStatus.WORKING,
                'location': {
                    'location': {
                        'lat': 53.907600,
                        'lng': 27.515333,
                    }
                }
            }, {
                'offline_happened_at': timestamp - 50,
                'work_status': WorkStatus.NOT_WORKING,
            }, {
                'offline_happened_at': timestamp,
                'work_status': WorkStatus.WORKING,
            }]
        )
        events = driver.events.all().filter(event=Event.CHANGED, field='work_status')
        events = list(events.order_by('happened_at'))

        self.assertEqual(len(events), 5)
        self.assertTrue(events[0].obj_dump and 'last_location' in events[0].obj_dump)
        self.assertEqual(events[0].new_value, WorkStatus.ON_BREAK)
        self.assertEqual(events[0].happened_at.timestamp(), timestamp - 100)

        self.assertTrue(events[1].obj_dump and 'last_location' in events[1].obj_dump)
        self.assertEqual(events[1].new_value, WorkStatus.NOT_WORKING)
        self.assertEqual(events[1].happened_at.timestamp(), timestamp - 90)

        self.assertTrue(events[2].obj_dump and 'last_location' in events[2].obj_dump)
        self.assertEqual(events[2].new_value, WorkStatus.WORKING)
        self.assertEqual(events[2].happened_at.timestamp(), timestamp - 80)

        self.assertTrue(events[3].obj_dump is None)
        self.assertEqual(events[3].new_value, WorkStatus.NOT_WORKING)
        self.assertEqual(events[3].happened_at.timestamp(), timestamp - 50)

        self.assertTrue(events[4].obj_dump is None)
        self.assertEqual(events[4].new_value, WorkStatus.WORKING)
        self.assertEqual(events[4].happened_at.timestamp(), timestamp)

    @patch('notification.celery_tasks.send_device_notification.delay')
    def test_update_driver_by_manager(self, send_notification):
        self.client.force_authenticate(self.manager)
        FCMDeviceFactory(user=self.driver)

        resp = self.client.patch(f'/api/users/{self.driver.id}/', {'first_name': 'New first name'})
        self.assertEqual(resp.status_code, HTTP_200_OK)
        self.assertEqual(send_notification.call_count, 1)
