from __future__ import absolute_import, unicode_literals

from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.forms import model_to_dict
from django.utils import timezone

from rest_framework.status import HTTP_200_OK

import mock

from base.factories import DriverFactory
from base.signals import post_bulk_create
from merchant_extension.models import Checklist, ResultChecklist
from notification.factories import FCMDeviceFactory
from notification.tests.base_test_cases import BaseDataPushNotificationTestCase
from reporting.models import Event
from tasks.celery_tasks import order_deadline_passed, send_notification_about_soon_deadline
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order
from tasks.models.terminate_code import TerminateCode, TerminateCodeConstants
from tasks.tests.base_test_cases import BaseOrderTestCase
from tasks.tests.factories import TerminateCodeFactory


class OrderChangesNotificationTestCaseV1(BaseOrderTestCase):
    version = 1

    @classmethod
    def setUpTestData(cls):
        super(OrderChangesNotificationTestCaseV1, cls).setUpTestData()
        cls.driver.first_name = 'Mr. Makedonov'
        cls.driver.save()
        cls.merchant.use_pick_up_status = True
        cls.merchant.use_way_back_status = True
        cls.merchant.save()
        cls.device = FCMDeviceFactory(user=cls.driver, api_version=cls.version)

    def setUp(self):
        self.order = self.create_default_order(driver=self.driver, status=OrderStatus.ASSIGNED)
        self.failing_order = self.create_default_order(driver=self.driver, status=OrderStatus.ASSIGNED)

    msgs = {
        st: {
            'type': 'JOB_{}'.format(st.upper())
        } for st in OrderStatus.status_groups.ALL
    }
    msgs[OrderStatus.NOT_ASSIGNED] = {'type': 'JOB_UNASSIGNED'}

    def get_message_kwargs(self, status, order, driver, initiator):
        texts = {
            OrderStatus.NOT_ASSIGNED: "{}, Job \"{}\" was unassigned from you".format(driver.first_name, order.title),
            OrderStatus.ASSIGNED: "{}, you have received a new job: \"{}\"".format(
                driver.first_name, order.deliver_address.address
            ),
            OrderStatus.IN_PROGRESS: "{}, your current job \"{}\" has been marked as \"In Progress\"{}".format(
                order.driver.first_name, order.title, initiator
            )
        }
        if status in texts.keys():
            data = {
                'text': texts[status],
                'is_concatenated_order': False,
            }
        else:
            data = {
                'text': "{}, your current job \"{}\" has been marked as \"{}\"{}".format(
                    order.driver.first_name, order.title, OrderStatus._status_dict[status].title(), initiator
                ),
                'is_concatenated_order': False,
            }
        if self.version == 1:
            data['order_id'] = order.order_id
        else:
            data['server_entity_id'] = order.id
        msg_kwargs = {'data': data}
        msg_kwargs.update(self.msgs[status])
        return msg_kwargs

    def get_message_bulk_assigned_kwargs(self, orders, driver):
        kw = {
            'type': "BULK_JOBS_ASSIGNED",
            'data': {
                'text': u"{}, you've received {} new jobs".format(driver.first_name, len(orders))
            }
        }
        if self.version == 1:
            kw['data']['orders_ids'] = [o.order_id for o in sorted(orders, key=lambda x: x.order_id)]
        else:
            kw['data']['server_entity_ids'] = [o.id for o in sorted(orders, key=lambda x: x.order_id)]
        return kw

    def get_message_deleted_kwargs(self, order_dump):
        kw = {
            'type': "JOB_DELETED",
            'data': {
                'text': u"{}, your job \"{}\" has been deleted".format(self.driver.first_name, order_dump['title']),
                'is_concatenated_order': False,
            }
        }
        if self.version == 1:
            kw['data']['order_id'] = order_dump.get('order_id')
        else:
            kw['data']['server_entity_id'] = order_dump.get('id')
        return kw

    def get_checklist_message(self, order):
        kw = {
            'type': 'OPEN_CHECKLIST',
            'data': {
                'is_concatenated_order': False,
                'text': 'Seems, that you\'ve arrived at job location. Please carry out the {}'
                    .format(order.driver_checklist.title),
            }
        }
        if self.version == 1:
            kw['data']['order_id'] = self.order.order_id
        else:
            kw['data']['server_entity_id'] = self.order.id
        return kw

    def get_nti_checklist_message(self, order):
        kwargs = self.get_checklist_message(order)
        kwargs['data']['text'] = 'You\'ve arrived at your job. Please carry out the {}'\
            .format(order.driver_checklist.title)

        return kwargs

    def set_order_url(self, order, author=None):
        version = self.version
        args = ('v{}/'.format(version), order.id) if version > 1 else ('', order.order_id)
        self.order_change_status_url = '/api/{}orders/{}/'.format(*args)
        if author:
            self.client.force_authenticate(author)

    def change_status_to(self, status, order):
        with mock.patch('notification.celery_tasks.send_device_notification.delay') as send_notification:
            data = {
                'status': status
            }
            if status == OrderStatus.ASSIGNED:
                data['driver'] = self.driver.id
            resp = self.client.patch(self.order_change_status_url, data)
            self.assertEqual(resp.status_code, HTTP_200_OK)
            self.assertDictEqual(
                send_notification.call_args[1]['message'],
                self.get_message_kwargs(status, order, self.driver, ' by the manager')
            )

    def change_status_by_driver(self, status):
        with mock.patch('notification.celery_tasks.send_device_notification.delay') as send_notification:
            data = {
                'status': status
            }
            resp = self.client.put(self.order_change_status_url + 'status/', data)
            self.assertEqual(resp.status_code, HTTP_200_OK)
            send_notification.assert_not_called()
            self.order.refresh_from_db()

    def test_status_notification(self):
        self.set_order_url(self.order, self.manager)
        for st in OrderStatus._merchant_available_statuses:
            # It is forbidden to change from delivered to failed
            if st != OrderStatus.FAILED:
                self.change_status_to(st, self.order)
        self.set_order_url(self.failing_order)
        self.change_status_to(OrderStatus.FAILED, self.failing_order)

    def test_reassing_job_notification(self):
        self.new_driver = DriverFactory(
            merchant=self.merchant,
            first_name='John',
            last_name='Doe'
        )
        self.new_device = FCMDeviceFactory(user=self.new_driver, api_version=self.version)

        self.set_order_url(self.order, self.manager)
        with mock.patch('notification.celery_tasks.send_device_notification.delay') as send_notification:
            data = {
                'driver': self.new_driver.id
            }
            resp = self.client.patch(self.order_change_status_url, data)
            self.assertEqual(resp.status_code, HTTP_200_OK)
            called_msgs_list = [kwargs['message'] for (args, kwargs) in send_notification.call_args_list]
            msgs_list = [
                self.get_message_kwargs(OrderStatus.NOT_ASSIGNED, self.order, self.driver, 'by manager'),
                self.get_message_kwargs(OrderStatus.ASSIGNED, self.order, self.new_driver, ' by manager')
            ]
            self.assertEqual(called_msgs_list, msgs_list)

    def test_driver_dont_receive_notifications(self):
        self.set_order_url(self.order, self.driver)

        for st in (OrderStatus.IN_PROGRESS, OrderStatus.WAY_BACK, OrderStatus.DELIVERED):
            self.change_status_by_driver(st)
        self.set_order_url(self.failing_order)
        self.change_status_by_driver(OrderStatus.FAILED)

    def test_bulk_assigned(self):
        ord_b = self.default_order_batch(size=3, status=OrderStatus.ASSIGNED)
        events = Event.objects.bulk_create(Event(object=o, event=Event.CREATED, merchant=o.merchant) for o in ord_b)
        with mock.patch('notification.celery_tasks.send_device_notification.delay') as send_notification:
            post_bulk_create.send(Event, instances=events)
            kw = self.get_message_bulk_assigned_kwargs(ord_b, self.driver)
            self.assertDictEqual(send_notification.call_args[1]['message'], kw)

    def test_deleted_notification(self):
        ctype = ContentType.objects.get_for_model(self.order.__class__)
        obj_dump = model_to_dict(self.order, fields=('driver', 'id', 'order_id', 'title', 'is_concatenated_order'))
        self.order.delete()
        with mock.patch('notification.celery_tasks.send_device_notification.delay') as send_notification:
            Event.objects.create(obj_dump=obj_dump, event=Event.DELETED, content_type=ctype, merchant=self.merchant)
            kw = self.get_message_deleted_kwargs(obj_dump)
            send_notification.assert_called()
            self.assertDictEqual(send_notification.call_args[1]['message'], kw)

    def _check_checklist_notification(self, get_message_function):
        self.set_order_url(self.order, author=self.driver)
        self.change_status_by_driver(OrderStatus.IN_PROGRESS)
        params = [self.version, self.order.order_id if self.version == 1 else self.order.id]
        with mock.patch('notification.celery_tasks.send_device_notification.delay') as send_notification:
            result_checklist = ResultChecklist.objects.create(checklist=Checklist.objects.create())
            self.order.driver_checklist = result_checklist
            self.order.save()
            resp = self.client.put('/api/v{}/orders/{}/geofence'.format(*params), {'geofence_entered': True})
            send_notification.assert_called()
            self.assertDictEqual(send_notification.call_args_list[0][1]['message'],
                                 get_message_function(self.order))
        self.assertEqual(resp.status_code, HTTP_200_OK)

    def test_checklist_notification(self):
        self._check_checklist_notification(self.get_checklist_message)

    def test_nti_checklist_notification(self):
        from merchant.models.mixins import MerchantTypes
        self.merchant.merchant_type = MerchantTypes.MERCHANT_TYPES.NTI
        self.merchant.save(update_fields=('merchant_type',))
        self._check_checklist_notification(self.get_nti_checklist_message)
        self.merchant.merchant_type = MerchantTypes.MERCHANT_TYPES.DEFAULT
        self.merchant.save(update_fields=('merchant_type',))

    def test_deadline_notifiers(self):
        _order = Order.objects.filter(id=self.order.id)
        _order.update(deliver_before=timezone.now() + timedelta(minutes=10),
                      driver=self.driver,
                      status=OrderStatus.ASSIGNED)
        with mock.patch('notification.celery_tasks.send_device_notification') as send_notification:
            send_notification_about_soon_deadline.delay()
            self.assertTrue(_order.filter(id=self.order.id, deadline_notified=True).exists())
            _order.update(deliver_before=timezone.now())
            order_deadline_passed.delay(self.order.id)
            message = {
                "data": {
                    "text": u"You have less than 30 minutes to finish job \"{}\"".format(self.order.title),
                    'is_concatenated_order': False,
                },
                "type": "JOB_DEADLINE"
            }
            if self.version == 1:
                message['data']['order_id'] = self.order.order_id
            else:
                message['data']['server_entity_id'] = self.order.id
            self.assertDictEqual(send_notification.call_args_list[0][1]['message'], message)
            message['data']['text'] = '{}, your job "{}" deadline has expired'.format(self.order.driver.first_name,
                                                                                        self.order.title)
            send_notification.assert_called()
            self.assertDictEqual(send_notification.call_args_list[1][1]['message'], message)

    def test_order_changed_notification(self):
        self.set_order_url(self.order, self.manager)
        with mock.patch('notification.celery_tasks.send_device_notification.delay') as send_notification:
            self.client.patch(self.order_change_status_url, data={'title': 'New title.'})
            self.order.refresh_from_db()
            message = {
                "data": {
                    "text": "{}, your job \"{}\" has been updated with new info".format(self.driver.first_name,
                                                                                         self.order.title),
                    'is_concatenated_order': False,
                }, "type": "JOB_CHANGED"
            }
            if self.version == 1:
                message['data']['order_id'] = self.order.order_id
            else:
                message['data']['server_entity_id'] = self.order.id
            send_notification.assert_called()
            self.assertDictEqual(send_notification.call_args[1]['message'], message)


class OrderChangesNotificationTestCaseV2(OrderChangesNotificationTestCaseV1):
    version = 2


class TerminateCodeEventNotificationTestCase(BaseDataPushNotificationTestCase):
    @classmethod
    def setUpTestData(cls):
        super(TerminateCodeEventNotificationTestCase, cls).setUpTestData()

    def setUp(self):
        self.client.force_authenticate(self.manager)
        self.terminate_code = TerminateCodeFactory(type=TerminateCodeConstants.TYPE_ERROR, merchant=self.merchant)
        self.message = self.get_message(self.terminate_code)

    def test_background_notification_on_code_creation(self):
        with mock.patch('notification.celery_tasks.send_device_notification.delay') as send_notification:
            data = {
                "name": "test_code",
                "type": TerminateCodeConstants.TYPE_ERROR
            }
            self.client.post('/api/terminate-codes/', data=data)
            self.assertTrue(send_notification.called)
            _, kwargs = send_notification.call_args
            new_terminate_code = TerminateCode.objects.get(name=data['name'])
            message = self.get_message(new_terminate_code)
            message['type'] = 'NEW_TERMINATECODE'
            self.assertDictEqual(kwargs['message'], message)
            self.assertEqual(kwargs['content_available'], True)

    def test_background_notification_on_code_change(self):
        with mock.patch('notification.celery_tasks.send_device_notification.delay') as send_notification:
            data = {
                "type": TerminateCodeConstants.TYPE_SUCCESS
            }
            self.client.patch('/api/terminate-codes/%s' % self.terminate_code.id, data=data)
            self.assertTrue(send_notification.called)
            _, kwargs = send_notification.call_args
            self.message['type'] = 'TERMINATECODE_CHANGED'
            self.assertDictEqual(kwargs['message'], self.message)
            self.assertEqual(kwargs['content_available'], True)

    def test_background_notification_on_code_deletion(self):
        with mock.patch('notification.celery_tasks.send_device_notification.delay') as send_notification:
            self.client.delete('/api/terminate-codes/%s' % self.terminate_code.id)
            self.assertTrue(send_notification.called)
            _, kwargs = send_notification.call_args
            self.message['type'] = 'TERMINATECODE_REMOVED'
            self.assertDictEqual(kwargs['message'], self.message)
            self.assertEqual(kwargs['content_available'], True)
