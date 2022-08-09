import io

from PIL import Image

from documents.tests.factories import TagFactory

from ...models import ConcatenatedOrder
from ..base_test_cases import BaseOrderTestCase


class OrderTestCase(BaseOrderTestCase):
    def setUp(self):
        self.order = self.create_default_order(sub_branding=self.sub_branding)
        self.driver = self.order.driver

    def _generate_image(self):
        file = io.BytesIO()
        image = Image.new('RGBA', size=(100, 100), color=(155, 0, 0))
        image.save(file, 'png')
        file.name = 'test.png'
        file.seek(0)
        return file

    def test_order_documents(self):
        document = self._generate_image()
        order = self.order
        driver = self.driver
        merchant = self.merchant
        tags = TagFactory.create_batch(merchant=merchant, size=3)

        order.status = order.ASSIGNED
        order.merchant = merchant
        order.save()

        self.client.force_authenticate(driver)

        path = '/api/mobile/orders/v1/{}/upload_confirmation_document/'.format(self.order.id)
        data = {
            'document': document,
            'name': 'bla',
            'tag_id': tags[0].id,
        }

        merchant.enable_delivery_confirmation_documents = False
        merchant.enable_delivery_confirmation = False
        merchant.save()
        document.seek(0)
        resp = self.client.patch(path, data=data, format='multipart')
        self.assertEqual(resp.status_code, 403)

        merchant.enable_delivery_confirmation_documents = True
        merchant.enable_delivery_confirmation = True
        merchant.save()
        document.seek(0)
        resp = self.client.patch(path, data=data, format='multipart')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['confirmation']['documents']), 1)
        order.refresh_from_db()
        self.assertEqual(order.order_confirmation_documents.count(), 1)
        self.assertEqual(order.order_confirmation_documents.first().tags.count(), 1)

        # Checking for duplicate banning
        resp = self.client.patch(path, data=data, format='multipart')
        self.assertEqual(resp.status_code, 400)

    def test_concatenated_order_documents(self):
        job_data = {
            'driver_id': self.driver.id,
            'deliver_address': {
                'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                'location': {
                    'lat': 53.91254758887667,
                    'lng': 27.543441765010357,
                }
            },
            'customer': {
                'name': 'Test20',
            },
        }

        self.merchant.driver_can_create_job = True
        self.merchant.enable_concatenated_orders = True
        self.merchant.enable_delivery_confirmation = True
        self.merchant.enable_delivery_confirmation_documents = True
        self.merchant.save()

        self.client.force_authenticate(self.driver)

        resp = self.client.post('/api/mobile/orders/v1/', data=job_data)
        self.assertEqual(resp.status_code, 201)
        resp = self.client.post('/api/mobile/orders/v1/', data=job_data)
        self.assertEqual(resp.status_code, 201)

        concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).last()

        document = self._generate_image()
        tags = TagFactory.create_batch(merchant=self.merchant, size=3)

        path = '/api/mobile/concatenated_orders/v1/{}/upload_confirmation_document/'.format(concatenated_order.id)
        data = {
            'document': document,
            'name': 'bla',
            'tag_id': [tags[0].id, tags[1].id]
        }

        resp = self.client.patch(path, data=data, format='multipart')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['confirmation']['documents']), 1)
        concatenated_order.refresh_from_db()
        self.assertEqual(concatenated_order.order_confirmation_documents.count(), 1)
        self.assertEqual(concatenated_order.order_confirmation_documents.first().tags.count(), 2)
        for order in concatenated_order.orders.all():
            self.assertEqual(order.order_confirmation_documents.count(), 1)
            self.assertEqual(order.order_confirmation_documents.first().tags.count(), 2)
