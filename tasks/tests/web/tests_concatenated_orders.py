from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from rest_framework import status
from rest_framework.test import APITestCase

import mock

from base.factories import DriverFactory, ManagerFactory
from merchant.factories import MerchantFactory, SkillSetFactory
from notification.factories import FCMDeviceFactory
from notification.tests.mixins import NotificationTestMixin
from reporting.context_managers import track_fields_on_change
from reporting.models import Event
from reporting.utils.delete import create_delete_event
from tasks.models import ConcatenatedOrder, Order


class ConcatenatedTestCase(APITestCase):
    orders_url = '/api/web/dev/orders/'
    concatenated_orders_url = '/api/web/dev/orders/'

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.merchant = MerchantFactory(
            enable_concatenated_orders=True,
            customer_review_opt_in_enabled=True,
            webhook_url=['example.com'],
            enable_skill_sets=True,
        )
        cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.driver = DriverFactory(merchant=cls.merchant)
        cls.events_qs = Event.objects.filter(
            content_type=ContentType.objects.get_for_model(ConcatenatedOrder, for_concrete_model=False)
        )
        cls.events_qs = cls.events_qs.exclude(event=Event.CHANGED).order_by('happened_at')

    def setUp(self):
        self.client.force_authenticate(self.manager)

    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_autogroup(self, push_mock):
        skill_set = SkillSetFactory(merchant=self.merchant)
        self.driver.skill_sets.add(skill_set)
        FCMDeviceFactory(user=self.driver, api_version=2)

        old_events_ids = list(self.events_qs.values_list('id', flat=True))

        # testing automatic creation concatenated order
        order_data = {
            'deliver': {
                'customer': {'name': 'Mike Kowalski'},
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                        'location': {'lat': 53.91254758887667, 'lng': 27.543441765010357},
                    },
                    'secondary_address': '27'
                }
            },
            'skill_set_ids': [skill_set.id],
        }

        with mock.patch('webhooks.celery_tasks.send_external_event') as send_external_event:
            resp = self.client.post(self.orders_url, data=order_data)
            concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).first()
            self.assertIsNone(concatenated_order)

            resp = self.client.post(self.orders_url, data=order_data)
            self.assertFalse(push_mock.called)  # Empty driver

            concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).first()
            self.assertIsNotNone(concatenated_order)
            self.assertEqual(self.events_qs.exclude(id__in=old_events_ids).count(), 1)  # created

            self.assertTrue(
                any(call.args[3] == 'concatenated_order.created' for call in send_external_event.call_args_list)
            )

        # testing automatic exit from a concatenated order and automatic deletion of a concatenated order
        old_events_ids = list(self.events_qs.values_list('id', flat=True))
        orders = list(concatenated_order.orders.all())

        resp = self.client.patch(f'{self.orders_url}{orders[0].id}/', {
            'driver_id': self.driver.id,
            'status': Order.ASSIGNED,
        })
        self.assertTrue(push_mock.called)
        push_mock.reset_mock()
        concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).first()
        self.assertIsNone(concatenated_order)
        # changed order and c_order and deleted
        self.assertEqual(self.events_qs.exclude(id__in=old_events_ids).count(), 3)

        # testing automatic attachment to a concatenated order
        old_events_ids = list(self.events_qs.values_list('id', flat=True))
        resp = self.client.patch(f'{self.orders_url}{orders[1].id}/', {
            'driver_id': self.driver.id,
            'status': Order.ASSIGNED,
        })
        self.assertTrue(push_mock.called)
        push_mock.reset_mock()
        concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).first()
        self.assertIsNotNone(concatenated_order)
        self.assertEqual(self.events_qs.exclude(id__in=old_events_ids).count(), 1)  # created

        # changing deliver date
        old_events_ids = list(self.events_qs.values_list('id', flat=True))
        resp = self.client.patch(f'{self.orders_url}{orders[1].id}/', {
            'deliver': {
                'before': timezone.now() + timedelta(days=2)
            }
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(push_mock.called)
        push_mock.reset_mock()
        concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).first()
        self.assertIsNone(concatenated_order)
        # changed order and c_order and deleted
        self.assertEqual(self.events_qs.exclude(id__in=old_events_ids).count(), 3)

    def test_changed_status_in_concatenated_api(self):
        old_events_ids = list(self.events_qs.values_list('id', flat=True))

        order_data_1 = {
            'deliver': {
                'customer': {'name': 'Mike Kowalski'},
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                        'location': {'lat': 53.91254758887667, 'lng': 27.543441765010357},
                    },
                    'secondary_address': '27'
                }
            }
        }
        self.client.post(self.orders_url, data=order_data_1)
        self.client.post(self.orders_url, data=order_data_1)
        self.assertEqual(self.events_qs.exclude(id__in=old_events_ids).count(), 1)  # created

        order_data_2 = {
            'deliver': {
                'customer': {'name': 'Djon Kowalski'},
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 3',
                        'location': {'lat': 53.91254758887667, 'lng': 27.543441765010357},
                    },
                    'secondary_address': '27'
                }
            }
        }
        self.client.post(self.orders_url, data=order_data_2)

        concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).first()
        self.assertIsNotNone(concatenated_order)

        nested_order = concatenated_order.orders.first()
        free_order = Order.objects.filter(merchant=self.merchant, concatenated_order__isnull=True).first()
        free_order.customer = nested_order.customer
        free_order.deliver_address = nested_order.deliver_address
        free_order.save()
        free_order.refresh_from_db()

        resp = self.client.patch(
            f'{self.concatenated_orders_url}{concatenated_order.id}/orders/',
            data={'order_ids': [free_order.id]}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(self.events_qs.exclude(id__in=old_events_ids).count(), 2)  # changed, added order

        resp = self.client.patch(
            f'{self.concatenated_orders_url}{concatenated_order.id}',
            data={'driver_id': self.driver.id, 'status': Order.ASSIGNED}
        )
        orders = list(Order.objects.filter(merchant=self.merchant))
        for order in orders:
            self.assertEqual(order.driver_id, self.driver.id)
            self.assertEqual(order.status, Order.ASSIGNED)
        self.assertEqual(self.events_qs.exclude(id__in=old_events_ids).count(), 3)  # changed

        resp = self.client.post(self.orders_url, data=order_data_2)
        nested_order = concatenated_order.orders.first()
        free_order_2 = Order.objects.get(id=resp.data['id'])
        free_order_2.customer = nested_order.customer
        free_order_2.deliver_address = nested_order.deliver_address
        free_order_2.save()
        free_order_2.refresh_from_db()

        resp = self.client.patch(
            f'{self.concatenated_orders_url}{concatenated_order.id}/orders/',
            data={'order_ids': [free_order_2.id]}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(self.events_qs.exclude(id__in=old_events_ids).count(), 4)  # changed, added unassigned
        self.assertEqual(Order.objects.get(id=free_order_2.id).status, Order.ASSIGNED)

        resp = self.client.patch(
            f'{self.concatenated_orders_url}{concatenated_order.id}',
            data={'driver_id': self.driver.id, 'status': Order.IN_PROGRESS}
        )
        orders = list(Order.objects.filter(merchant=self.merchant))
        for order in orders:
            self.assertEqual(order.driver_id, self.driver.id)
            self.assertEqual(order.status, Order.IN_PROGRESS)
        self.assertEqual(self.events_qs.exclude(id__in=old_events_ids).count(), 5)  # changed

    def test_concatenated_update(self):
        old_events_ids = list(self.events_qs.values_list('id', flat=True))

        order_data = {
            'deliver': {
                'customer': {'name': 'Mike Kowalski'},
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                        'location': {'lat': 53.91254758887667, 'lng': 27.543441765010357},
                    },
                    'secondary_address': '27'
                }
            }
        }
        resp = self.client.post(self.orders_url, data=order_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        resp = self.client.post(self.orders_url, data=order_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).last()
        self.assertEqual(self.events_qs.exclude(id__in=old_events_ids).count(), 1)  # created

        new_concatenated_order_data = {
            'deliver': {
                'customer': {
                    'name': 'Bla',
                    'email': 'email@example.com'
                },
                'address': {
                    'primary_address': {
                        'address': 'Bla',
                        'location': {
                            'lat': 53.91254758887667,
                            'lng': 27.543441765010357
                        },
                    },
                    'secondary_address': '11'
                }
            }
        }
        resp = self.client.patch(
            f'{self.concatenated_orders_url}{concatenated_order.id}/',
            data=new_concatenated_order_data,
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(self.events_qs.exclude(id__in=old_events_ids).count(), 2)  # changed

        resp = self.client.delete(f'{self.concatenated_orders_url}{concatenated_order.id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.events_qs.exclude(id__in=old_events_ids).count(), 3)  # deleted

    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_concatenated_api(self, push_mock):
        order_data = {
            'deliver': {
                'customer': {'name': 'Mike Kowalski'},
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                        'location': {'lat': 53.91254758887667, 'lng': 27.543441765010357},
                    },
                    'secondary_address': '27'
                }
            },
            'status': 'assigned',
            'driver_id': self.driver.id,
        }
        resp = self.client.post(self.orders_url, data=order_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        order_1 = Order.objects.get(id=resp.data['id'])
        resp = self.client.post(self.orders_url, data=order_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        order_2 = Order.objects.get(id=resp.data['id'])
        resp = self.client.post(self.orders_url, data=order_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        order_3 = Order.objects.get(id=resp.data['id'])

        concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).first()

        push_mock.reset_mock()
        resp = self.client.put(
            f'{self.concatenated_orders_url}{concatenated_order.id}/orders/',
            data={'order_ids': [order_1.id, order_2.id]}
        )
        self.assertEqual(len(resp.data['orders']), 2)
        self.assertTrue(push_mock.called)
        push_mock.reset_mock()

        resp = self.client.patch(
            f'{self.concatenated_orders_url}{concatenated_order.id}/orders/',
            data={'order_ids': [order_3.id]}
        )
        self.assertEqual(len(resp.data['orders']), 3)
        self.assertTrue(push_mock.called)
        push_mock.reset_mock()

        resp = self.client.delete(
            f'{self.concatenated_orders_url}{concatenated_order.id}/orders/',
            data={'order_ids': [order_1.id]}
        )
        self.assertEqual(len(resp.data['orders']), 2)
        self.assertTrue(push_mock.called)
        push_mock.reset_mock()

        resp = self.client.get(f'{self.concatenated_orders_url}{concatenated_order.id}/orders/')
        self.assertEqual(resp.data['count'], 2)
        self.assertFalse(push_mock.called)
        push_mock.reset_mock()

        resp = self.client.get(f'{self.concatenated_orders_url}{concatenated_order.id}/available_orders/')
        self.assertEqual(resp.data['count'], 1)

        resp = self.client.get(f'{self.concatenated_orders_url}{concatenated_order.id}/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.delete(f'{self.concatenated_orders_url}{concatenated_order.id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

    def test_pickup_status_in_concatenated_api(self):
        self.merchant.use_pick_up_status = True
        self.merchant.save()

        order_data = {
            'deliver': {
                'customer': {'name': 'Mike Kowalski'},
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                        'location': {'lat': 53.91254758887667, 'lng': 27.543441765010357},
                    },
                    'secondary_address': '27'
                }
            },
            'pickup': {
                'customer': {'name': 'Djon'},
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Brest, Belarus 312',
                        'location': {'lat': 53.91254758887667, 'lng': 27.543441765010357},
                    },
                    'secondary_address': '27'
                }
            },
            'status': 'assigned',
            'driver_id': self.driver.id,
        }
        resp = self.client.post(self.orders_url, data=order_data)
        resp = self.client.post(self.orders_url, data=order_data)
        resp = self.client.post(self.orders_url, data=order_data)
        order_with_pickup_id = resp.data['id']

        order_data_2 = {
            'deliver': {
                'customer': {'name': 'Mike Kowalski'},
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                        'location': {'lat': 53.91254758887667, 'lng': 27.543441765010357},
                    },
                    'secondary_address': '27'
                }
            },
            'status': Order.ASSIGNED,
            'driver_id': self.driver.id,
        }
        resp = self.client.post(self.orders_url, data=order_data_2)
        order_for_failed_id = resp.data['id']

        concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).first()
        self.assertIsNotNone(concatenated_order)
        self.assertEqual(concatenated_order.orders.all().filter(status=Order.ASSIGNED).count(), 4)
        # Three jobs automatically formed a concatenated order

        resp = self.client.patch(
            f'{self.orders_url}{order_with_pickup_id}',
            data={'status': Order.PICK_UP}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(concatenated_order.orders.all().count(), 3)
        # One jobs changed its status and automatically exited the concatenated order

        resp = self.client.patch(
            f'{self.concatenated_orders_url}{concatenated_order.id}',
            data={'status': Order.PICK_UP}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(concatenated_order.orders.all().filter(status=Order.ASSIGNED).count(), 1)
        self.assertEqual(concatenated_order.orders.all().filter(status=Order.PICK_UP).count(), 2)
        # Not all jobs can be in pickup status, but they remain in a concatenated order

        resp = self.client.patch(
            f'{self.concatenated_orders_url}{concatenated_order.id}',
            data={'status': Order.IN_PROGRESS}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(concatenated_order.orders.all().filter(status=Order.IN_PROGRESS).count(), 3)

        with mock.patch('tasks.models.orders.Order.notify_customer') as mock_notify:
            resp = self.client.patch(
                f'{self.orders_url}{order_for_failed_id}',
                data={'status': Order.FAILED}
            )
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertEqual(concatenated_order.orders.all().filter(status=Order.IN_PROGRESS).count(), 2)
            self.assertEqual(concatenated_order.orders.all().count(), 3)
            # Failed orders remain in the concatenated order
            mock_notify.assert_called_once()

        resp = self.client.patch(
            f'{self.concatenated_orders_url}{concatenated_order.id}',
            data={'status': Order.DELIVERED}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(concatenated_order.orders.all().filter(status=Order.DELIVERED).count(), 2)
        self.assertEqual(concatenated_order.orders.all().count(), 3)

    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_empty_concatenated_order(self, push_mock):
        old_events_ids = list(self.events_qs.values_list('id', flat=True))
        order_data = {
            'deliver': {
                'customer': {'name': 'Mike Kowalski'},
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                        'location': {'lat': 53.91254758887667, 'lng': 27.543441765010357},
                    },
                    'secondary_address': '27'
                }
            }
        }
        resp = self.client.post(self.orders_url, data=order_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        order_1 = Order.objects.get(id=resp.data['id'])
        resp = self.client.post(self.orders_url, data=order_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        order_2 = Order.objects.get(id=resp.data['id'])
        self.assertEqual(self.events_qs.exclude(id__in=old_events_ids).count(), 1)  # created

        concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).first()

        resp = self.client.delete(
            f'{self.concatenated_orders_url}{concatenated_order.id}/orders/',
            data={'order_ids': [order_1.id, order_2.id]}
        )
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.events_qs.exclude(id__in=old_events_ids).count(), 3)  # changed and deleted

        resp = self.client.get(f'{self.concatenated_orders_url}{concatenated_order.id}/')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_skill_sets(self):
        skill_set_1 = SkillSetFactory(merchant=self.merchant)
        skill_set_2 = SkillSetFactory(merchant=self.merchant)
        skill_set_3 = SkillSetFactory(merchant=self.merchant)
        self.driver.skill_sets.add(skill_set_1, skill_set_2, skill_set_3)

        invalid_driver = DriverFactory(merchant=self.merchant)

        order_data = {
            'deliver': {
                'customer': {'name': 'Mike Kowalski'},
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                        'location': {'lat': 53.91254758887667, 'lng': 27.543441765010357},
                    },
                }
            },
        }
        resp = self.client.post(self.orders_url, data={**order_data, 'skill_set_ids': [skill_set_1.id, skill_set_2.id]})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        resp = self.client.post(self.orders_url, data={**order_data, 'skill_set_ids': [skill_set_2.id, skill_set_3.id]})
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).first()

        resp = self.client.patch(
            f'{self.concatenated_orders_url}{concatenated_order.id}',
            data={'driver_id': invalid_driver.id, 'status': Order.ASSIGNED}
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        resp = self.client.patch(
            f'{self.concatenated_orders_url}{concatenated_order.id}',
            data={'driver_id': self.driver.id, 'status': Order.ASSIGNED}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_confirm_by_customer(self):
        old_events_ids = list(self.events_qs.values_list('id', flat=True))

        order_data = {
            'driver_id': self.driver.id,
            'deliver': {
                'customer': {'name': 'Mike Kowalski'},
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                        'location': {'lat': 53.91254758887667, 'lng': 27.543441765010357},
                    },
                    'secondary_address': '27'
                }
            }
        }
        self.client.post(self.orders_url, data=order_data)
        self.client.post(self.orders_url, data=order_data)
        self.assertEqual(self.events_qs.exclude(id__in=old_events_ids).count(), 1)  # created

        concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).first()
        self.assertIsNotNone(concatenated_order)
        concatenated_order.status = concatenated_order.IN_PROGRESS
        concatenated_order.save()

        self.client.force_authenticate(None)
        customer_order_confirmation_url = '/api/customers/{}/orders/{}/confirmation/'.format(
            urlsafe_base64_encode(force_bytes(concatenated_order.customer_id)),
            concatenated_order.order_token,
        )
        confirmation_data = {
            'is_confirmed_by_customer': True,
            'customer_review_opt_in': True,
            'rating': 5,
            'customer_comment': 'Hi',
        }
        resp = self.client.patch(customer_order_confirmation_url, data=confirmation_data)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        concatenated_order.refresh_from_db()

        for field, value in confirmation_data.items():
            self.assertEqual(getattr(concatenated_order, field), value)

        for order in concatenated_order.orders.all():
            for field, value in confirmation_data.items():
                self.assertEqual(getattr(order, field), value)

    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_notify_customer(self, push_mock):
        old_events_ids = list(self.events_qs.values_list('id', flat=True))

        order_data = {
            'driver_id': self.driver.id,
            'deliver': {
                'customer': {'name': 'Mike Kowalski'},
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                        'location': {'lat': 53.91254758887667, 'lng': 27.543441765010357},
                    },
                    'secondary_address': '27'
                }
            }
        }
        self.client.post(self.orders_url, data=order_data)
        self.client.post(self.orders_url, data=order_data)
        self.assertEqual(self.events_qs.exclude(id__in=old_events_ids).count(), 1)  # created

        concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).first()
        self.assertIsNotNone(concatenated_order)

        with mock.patch('tasks.models.orders.Order.notify_customer') as mock_notify:
            resp = self.client.patch(
                f'{self.concatenated_orders_url}{concatenated_order.id}',
                data={'status': Order.IN_PROGRESS}
            )
        self.assertEqual(mock_notify.call_count, 1)

    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_nested_orders_removing(self, push_mock):
        order_data = {
            'driver_id': self.driver.id,
            'deliver': {
                'customer': {'name': 'Mike Kowalski'},
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                        'location': {'lat': 53.91254758887667, 'lng': 27.543441765010357},
                    },
                    'secondary_address': '27'
                }
            }
        }
        self.client.post(self.orders_url, data=order_data)
        self.client.post(self.orders_url, data=order_data)
        self.client.post(self.orders_url, data=order_data)
        self.client.post(self.orders_url, data=order_data)
        self.client.post(self.orders_url, data=order_data)
        self.assertTrue(push_mock.called)
        push_mock.reset_mock()

        concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).first()
        self.assertIsNotNone(concatenated_order)
        self.assertEqual(concatenated_order.orders.count(), 5)

        order_1 = concatenated_order.orders.all().first()
        resp = self.client.delete(f'{self.orders_url}{order_1.id}/')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(concatenated_order.orders.count(), 4)

        order_2 = concatenated_order.orders.all().first()
        with track_fields_on_change(order_2, initiator=self.manager):
            order_2.safe_delete()
        self.assertEqual(concatenated_order.orders.count(), 3)

        order_3 = concatenated_order.orders.all().first()
        create_delete_event(self, order_3, self.manager)
        order_3.delete()
        self.assertEqual(concatenated_order.orders.count(), 2)

    def test_recalculating_delivery_interval_after_failed_job(self):
        order_data = {
            'driver_id': self.driver.id,
            'deliver': {
                'customer': {'name': 'Mike Kowalski'},
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                        'location': {'lat': 53.91254758887667, 'lng': 27.543441765010357},
                    },
                    'secondary_address': '27'
                }
            }
        }

        time = timezone.now() + timedelta(minutes=100)

        order_data['deliver']['before'] = time
        resp = self.client.post(self.orders_url, data=order_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        order_id_1 = resp.data['id']

        order_data['deliver']['before'] = time + timedelta(minutes=1)
        resp = self.client.post(self.orders_url, data=order_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        order_data['deliver']['before'] = time + timedelta(minutes=2)
        resp = self.client.post(self.orders_url, data=order_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).first()
        self.assertEqual(concatenated_order.deliver_before, time)

        resp = self.client.patch(f'{self.orders_url}{order_id_1}/', {'status': Order.FAILED})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        concatenated_order.refresh_from_db()
        self.assertEqual(concatenated_order.deliver_before, time + timedelta(minutes=1))

    @NotificationTestMixin.make_push_available
    @NotificationTestMixin.mock_send_versioned_push_decorator
    def test_auto_group_concatenated_change_status(self, push_mock):
        order_data = {
            'deliver': {
                'customer': {'name': 'Mike Kowalski'},
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                        'location': {'lat': 53.91254758887667, 'lng': 27.543441765010357},
                    },
                    'secondary_address': '27'
                }
            }
        }
        self.client.post(self.orders_url, data=order_data)
        self.client.post(self.orders_url, data=order_data)
        resp = self.client.post(self.orders_url, data=order_data)
        order_id = resp.data['id']
        self.assertFalse(push_mock.called)  # Empty driver

        concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).first()

        order = Order.objects.get(id=order_id)
        self.assertIsNotNone(order.concatenated_order_id)

        self.client.patch(f'{self.orders_url}{order_id}/', {
            'driver_id': self.driver.id,
            'status': Order.ASSIGNED,
        })
        order.refresh_from_db()
        self.assertIsNone(order.concatenated_order_id)
        self.assertTrue(push_mock.called)
        push_mock.reset_mock()

        self.client.patch(f'{self.concatenated_orders_url}{concatenated_order.id}/', {
            'driver_id': self.driver.id,
            'status': Order.ASSIGNED,
        })
        order.refresh_from_db()
        self.assertIsNotNone(order.concatenated_order_id)
        self.assertTrue(push_mock.called)
        push_mock.reset_mock()
