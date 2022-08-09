from datetime import timedelta

from django.utils import timezone

from driver.factories import DriverLocationFactory
from merchant.factories import LabelFactory, SkillSetFactory, SubBrandingFactory

from ...models import Order
from ..base_test_cases import BaseOrderTestCase


class WebOrderTestCase(BaseOrderTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.merchant.use_subbranding = True
        cls.merchant.enable_labels = True
        cls.merchant.enable_skill_sets = True
        cls.merchant.option_barcodes = cls.merchant.TYPES_BARCODES.both
        cls.merchant.use_pick_up_status = True
        cls.merchant.use_way_back_status = True
        cls.merchant.enable_delivery_confirmation = True
        cls.merchant.enable_delivery_pre_confirmation = True
        cls.merchant.enable_pick_up_confirmation = True
        cls.merchant.enable_delivery_confirmation_documents = True
        cls.merchant.enable_skids = True
        cls.merchant.enable_job_description = True
        cls.merchant.save()
        loc = DriverLocationFactory(member=cls.driver)
        cls.driver.last_location = loc
        cls.driver.save()
        cls.job_data = {
            'title': 'New job',
            'description': '1231',
            'comment': 'Comment',
            'deliver': {
                'customer': {
                    'name': 'Mike Kowalski',
                    'phone_number': '+61444444444',
                    'email': 'email@example.com'
                },
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                        'location': {
                            'lat': 53.91254758887667,
                            'lng': 27.543441765010357
                        },
                    },
                    'secondary_address': '27'
                },
                'after': timezone.now() + timedelta(days=10, minutes=3),
                'before': timezone.now() + timedelta(days=10, minutes=4),
            },
        }
        cls.labels = LabelFactory.create_batch(merchant=cls.merchant, size=3)

        cls.skill_sets = SkillSetFactory.create_batch(merchant=cls.merchant, size=3)
        cls.driver.skill_sets.add(cls.skill_sets[0])

        cls.secret_skill_sets = SkillSetFactory.create_batch(merchant=cls.merchant, is_secret=True, size=3)
        cls.driver.skill_sets.add(cls.secret_skill_sets[0])

        cls.sub_branding = SubBrandingFactory(merchant=cls.merchant)

    def test_create_order(self):
        self.client.force_authenticate(self.manager)

        resp = self.client.post('/api/web/dev/orders/', data=self.job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(id=resp.data['id']).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.status, Order.NOT_ASSIGNED)

    def test_create_order_with_everything(self):
        self.client.force_authenticate(self.manager)
        job_data = {
            'title': 'New job',
            'description': '1231',
            'comment': 'Comment',
            'driver_id': self.driver.id,
            'pickup': {
                'customer': {
                    'name': 'Azamat Musagaliyev',
                    'phone_number': '61444444444',
                    'email': 'email@example.com'
                },
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                        'location': {
                            'lat': 53.91254758887667,
                            'lng': 27.543441765010357
                        },
                    },
                    'secondary_address': '27'
                },
                'after': timezone.now() + timedelta(days=10, minutes=1),
                'before': timezone.now() + timedelta(days=10, minutes=2),
            },
            'deliver': {
                'customer': {
                    'name': 'Mike Kowalski',
                    'phone_number': '61444444444',
                    'email': 'email@example.com'
                },
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                        'location': {
                            'lat': 53.91254758887667,
                            'lng': 27.543441765010357
                        },
                    },
                    'secondary_address': '27'
                },
                'after': timezone.now() + timedelta(days=10, minutes=3),
                'before': timezone.now() + timedelta(days=10, minutes=4),
            },
            'status': 'assigned',
            'sub_branding_id': self.sub_branding.id,
            'label_ids': [self.labels[0].id, self.labels[1].id],
            'skill_set_ids': [self.skill_sets[0].id],
            'barcodes': [
                {
                    'id': 123,
                    'code_data': 'unique letter combination #22',
                    'required': False
                }
            ]
        }
        resp = self.client.post('/api/web/dev/orders/', data=job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(id=resp.data['id'], driver=self.driver).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.status, Order.ASSIGNED)

        # check edit barcodes
        barcode = order.barcodes.all().first()
        data = {
            'barcodes': [
                {
                    'id': barcode.id,
                    'code_data': 'changed unique letter combination #22',
                }
            ]
        }
        resp = self.client.patch(f'/api/web/dev/orders/{order.id}/', data=data)
        order.refresh_from_db()
        barcode.refresh_from_db()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(barcode.code_data, data['barcodes'][0]['code_data'])
        self.assertEqual(order.barcodes.all().count(), 1)

        # check delete barcodes
        data = {
            'barcodes': [
                {
                    'id': barcode.id,
                }
            ]
        }
        resp = self.client.patch(f'/api/web/dev/orders/{order.id}/', data=data)
        order.refresh_from_db()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(order.barcodes.all().count(), 0)

        # check add barcodes
        data = {
            'barcodes': [
                {
                    'code_data': 'add unique letter combination #22',
                }
            ]
        }
        resp = self.client.patch(f'/api/web/dev/orders/{order.id}/', data=data)
        order.refresh_from_db()
        barcode = order.barcodes.all().first()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(barcode.code_data, data['barcodes'][0]['code_data'])
        self.assertEqual(order.barcodes.all().count(), 1)

    def test_create_order_with_minimal_functionality(self):
        self.merchant.use_subbranding = False
        self.merchant.enable_labels = False
        self.merchant.enable_skill_sets = False
        self.merchant.option_barcodes = self.merchant.TYPES_BARCODES.disable
        self.merchant.use_pick_up_status = False
        self.merchant.use_way_back_status = False
        self.merchant.enable_delivery_confirmation = False
        self.merchant.enable_delivery_pre_confirmation = False
        self.merchant.enable_pick_up_confirmation = False
        self.merchant.enable_delivery_confirmation_documents = False
        self.merchant.enable_skids = False
        self.merchant.enable_job_description = False
        self.merchant.save()

        self.client.force_authenticate(self.manager)
        job_data = {
            'title': 'New job',
            'description': '1231',
            'comment': 'Comment',
            'driver_id': self.driver.id,
            'pickup': {
                'customer': {
                    'name': 'Azamat Musagaliyev',
                    'phone_number': '61444444444',
                    'email': 'email@example.com'
                },
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                        'location': {
                            'lat': 53.91254758887667,
                            'lng': 27.543441765010357
                        },
                    },
                    'secondary_address': '27'
                },
                'after': timezone.now() + timedelta(days=10, minutes=1),
                'before': timezone.now() + timedelta(days=10, minutes=2),
            },
            'deliver': {
                'customer': {
                    'name': 'Mike Kowalski',
                    'phone_number': '61444444444',
                    'email': 'email@example.com'
                },
                'address': {
                    'primary_address': {
                        'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                        'location': {
                            'lat': 53.91254758887667,
                            'lng': 27.543441765010357
                        },
                    },
                    'secondary_address': '27'
                },
                'after': timezone.now() + timedelta(days=10, minutes=3),
                'before': timezone.now() + timedelta(days=10, minutes=4),
            },
            'status': 'assigned',
            'sub_branding_id': self.sub_branding.id,
            'label_ids': [self.labels[0].id, self.labels[1].id],
            'skill_set_ids': [self.skill_sets[0].id],
            'barcodes': [
                {
                    'code_data': 'unique letter combination #22',
                    'required': False
                }
            ]
        }
        resp = self.client.post('/api/web/dev/orders/', data=job_data)
        self.assertEqual(resp.status_code, 201)
        order = Order.objects.filter(id=resp.data['id'], driver=self.driver).first()
        self.assertIsNotNone(order)
        self.assertEqual(order.status, Order.ASSIGNED)

        resp = self.client.get(f"/api/web/dev/orders/{resp.data['id']}/path/")
        self.assertEqual(resp.status_code, 200)

    def test_get_last_customer_comments(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/web/dev/orders/last_customer_comments/')
        self.assertEqual(resp.status_code, 200)

    def test_get_ids(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/web/dev/orders/ids/')
        self.assertEqual(resp.status_code, 200)

    def test_get_deadlines(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/web/dev/orders/deadlines/')
        self.assertEqual(resp.status_code, 200)

    def test_get_count_items(self):
        self.client.force_authenticate(self.manager)
        resp = self.client.get('/api/web/dev/orders/count_items/')
        self.assertEqual(resp.status_code, 200)
