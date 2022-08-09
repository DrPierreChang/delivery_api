import io

from django.utils import timezone

from rest_framework import status

import mock
from PIL import Image

from driver.factories import DriverLocationFactory
from merchant_extension.factories import AnswerFactory, ChecklistFactory, QuestionFactory, SectionFactory
from merchant_extension.models import Question, ResultChecklist
from reporting.models import Event

from ...mixins.order_status import OrderStatus
from ...models import ConcatenatedOrder, Order
from ..base_test_cases import BaseOrderTestCase


class MobileOrderUpdateTestCase(BaseOrderTestCase):
    @classmethod
    def setUpTestData(cls):
        super(MobileOrderUpdateTestCase, cls).setUpTestData()
        loc = DriverLocationFactory(member=cls.driver)
        cls.driver.last_location = loc
        cls.driver.save()

        cls.job_data = {
            'deliver_address': {
                'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                'location': {
                    'lat': 53.91254758887667,
                    'lng': 27.543441765010357,
                },
            },
            'customer': {
                'name': 'Test20',
            },
            'pickup_address': {
                'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                'location': {
                    'lat': 53.91254758887667,
                    'lng': 27.543441765010357,
                },
            },
            'pickup': {
                'name': 'Test20',
            },
        }

        cls.checklist = ChecklistFactory()
        cls.checklist_section = SectionFactory(checklist=cls.checklist)
        cls.questions = QuestionFactory.create_batch(
            section=cls.checklist_section,
            category=Question.DICHOTOMOUS,
            size=2
        )
        for question in cls.questions:
            AnswerFactory(question=question, text=True, is_correct=True)

    def _generate_image(self):
        file = io.BytesIO()
        image = Image.new('RGBA', size=(100, 100), color=(155, 0, 0))
        image.save(file, 'png')
        file.name = 'test.png'
        file.seek(0)
        return file

    def answer_checklist(self, checklist_id):
        resp = self.client.get(f'/api/mobile/checklists/v1/{checklist_id}/')

        for question in resp.data['checklist']['questions']:
            answer = {
                'question': question['id'],
                'choice': True,
                'comment': 'comment for %s' % question['id'],
                'answer_photos': self._generate_image()
            }
            resp = self.client.post(
                f'/api/mobile/checklists/v1/{checklist_id}/answer/', data=answer, format='multipart',
            )
            self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        resp = self.client.put(f'/api/mobile/checklists/v1/{checklist_id}/confirm/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_workflow_order(self):
        self.merchant.enable_concatenated_orders = True
        self.merchant.advanced_completion = self.merchant.ADVANCED_COMPLETION_REQUIRED
        self.merchant.driver_can_create_job = True
        self.merchant.option_barcodes = self.merchant.TYPES_BARCODES.both
        self.merchant.use_pick_up_status = True
        self.merchant.in_app_jobs_assignment = True
        self.merchant.enable_delivery_pre_confirmation = True
        self.merchant.enable_delivery_confirmation = True
        self.merchant.enable_pick_up_confirmation = True
        self.merchant.enable_delivery_confirmation_documents = True
        self.merchant.use_way_back_status = True
        self.merchant.enable_job_description = True
        self.merchant.checklist = self.checklist
        self.merchant.save()

        self.client.force_authenticate(self.driver)

        events_qs = Event.objects.exclude(event=Event.CHANGED).order_by('happened_at')

        # create orders
        path = '/api/mobile/orders/v1/'
        resp = self.client.post(path, data=self.job_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        resp = self.client.post(path, data=self.job_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        resp = self.client.post(path, data=self.job_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        for_delete_order_id = resp.data['server_entity_id']

        concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).last()
        self.assertIsNotNone(concatenated_order)
        self.assertEqual(concatenated_order.status, Order.NOT_ASSIGNED)
        co_path = f'/api/mobile/concatenated_orders/v1/{concatenated_order.id}/'

        resp = self.client.get(co_path)
        self.assertTrue('customer' in resp.data)

        # testing assigned and unassigned
        resp = self.client.patch(co_path, data={'status': OrderStatus.ASSIGNED, 'driver_id': self.driver.id})
        concatenated_order.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(concatenated_order.status, OrderStatus.ASSIGNED)

        resp = self.client.patch(co_path, data={'status': OrderStatus.NOT_ASSIGNED})
        concatenated_order.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(concatenated_order.status, OrderStatus.NOT_ASSIGNED)
        self.assertIsNone(concatenated_order.driver)

        exists_e_ids = list(events_qs.values_list('id', flat=True))
        resp = self.client.patch(co_path, data={'status': OrderStatus.ASSIGNED, 'driver_id': self.driver.id})
        concatenated_order.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(concatenated_order.status, OrderStatus.ASSIGNED)
        events = events_qs.exclude(id__in=exists_e_ids)
        self.assertEqual(events.count(), 4)

        resp = self.client.patch(f'{path}{for_delete_order_id}/', data={'status': OrderStatus.FAILED})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # testing checklist
        resp = self.client.get(co_path)
        self.assertFalse(resp.data['checklist']['checklist_passed'])

        exists_e_ids = list(events_qs.values_list('id', flat=True))
        self.answer_checklist(concatenated_order.driver_checklist_id)
        events = events_qs.exclude(id__in=exists_e_ids)
        self.assertEqual(events.count(), 3)

        resp = self.client.get(co_path)
        self.assertTrue(resp.data['checklist']['checklist_passed'])
        for order in concatenated_order.orders.all():
            resp = self.client.get(path + f'{order.id}/')
            if order.status != OrderStatus.FAILED:
                self.assertTrue(resp.data['checklist']['checklist_passed'])
            else:
                self.assertFalse(resp.data['checklist']['checklist_passed'])

        checklists = ResultChecklist.objects.filter(checklist=self.checklist)
        for checklist in checklists:
            for answer in checklist.result_answers.all():
                self.assertTrue(answer.photos.exists())

        resp = self.client.patch(co_path, data={'completion': {'code_ids': [201]}})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # testing pickup
        resp = self.client.patch(co_path, data={'status': OrderStatus.PICK_UP})
        concatenated_order.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(concatenated_order.status, OrderStatus.PICK_UP)

        # testing pickup confirmation
        image_5 = self._generate_image()
        image_6 = self._generate_image()
        resp = self.client.patch(
            co_path + 'upload_images/',
            data={
                'pick_up_confirmation_signature': image_5,
                'pick_up_confirmation_photos': image_6,
                'pick_up_confirmation_comment': 'Pick up comment',
                'offline_happened_at': timezone.now().timestamp(),
            },
            format='multipart',
        )
        concatenated_order.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertNotEqual(concatenated_order.pick_up_confirmation_signature, None)
        self.assertTrue(concatenated_order.pick_up_confirmation_photos.exists())
        self.assertEqual(concatenated_order.pick_up_confirmation_comment, 'Pick up comment')

        for order in concatenated_order.orders.all():
            if order.status != OrderStatus.FAILED:
                self.assertTrue(bool(order.pick_up_confirmation_signature))
                self.assertTrue(order.pick_up_confirmation_photos.exists())
                self.assertEqual(order.pick_up_confirmation_comment, 'Pick up comment')
            else:
                self.assertFalse(bool(order.pick_up_confirmation_signature))
                self.assertFalse(order.pick_up_confirmation_photos.exists())
                self.assertNotEqual(order.pick_up_confirmation_comment, 'Pick up comment')

        resp = self.client.patch(co_path, data={
            'status': 'in_progress',
            'starting_point': {
                'address': 'Fake address',
                'location': {
                    'lat': 55.5,
                    'lng': 27.5,
                },
            },
        })
        concatenated_order.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(concatenated_order.starting_point)
        self.assertEqual(concatenated_order.status, Order.IN_PROGRESS)
        for order in concatenated_order.orders.all():
            if order.status != OrderStatus.FAILED:
                self.assertIsNotNone(order.starting_point)
                self.assertEqual(order.status, Order.IN_PROGRESS)
            else:
                self.assertIsNone(order.starting_point)
                self.assertNotEqual(order.status, Order.IN_PROGRESS)

        # testing in progress
        resp = self.client.patch(co_path, data={
            'status': 'in_progress',
            'starting_point': None,
        })
        concatenated_order.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # testing confirmations
        image_1 = self._generate_image()
        image_2 = self._generate_image()
        image_3 = self._generate_image()
        image_4 = self._generate_image()
        resp = self.client.patch(
            co_path + 'upload_images/',
            data={
                'pre_confirmation_signature': image_1,
                'pre_confirmation_photos': image_2,
                'pre_confirmation_comment': 'Pre comment',
                'confirmation_signature': image_3,
                'confirmation_photos': image_4,
                'confirmation_comment': 'Comment',
                'offline_happened_at': timezone.now().timestamp(),
            },
            format='multipart',
        )
        concatenated_order.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertIsNotNone(concatenated_order.pre_confirmation_signature)
        self.assertTrue(concatenated_order.pre_confirmation_photos.exists())
        self.assertEqual(concatenated_order.pre_confirmation_comment, 'Pre comment')

        for order in concatenated_order.orders.all():
            if order.status != OrderStatus.FAILED:
                self.assertTrue(bool(order.pre_confirmation_signature))
                self.assertTrue(order.pre_confirmation_photos.exists())
                self.assertEqual(order.pre_confirmation_comment, 'Pre comment')
            else:
                self.assertFalse(bool(order.pre_confirmation_signature))
                self.assertFalse(order.pre_confirmation_photos.exists())
                self.assertNotEqual(order.pre_confirmation_comment, 'Pre comment')

        self.assertIsNotNone(concatenated_order.confirmation_signature)
        self.assertTrue(concatenated_order.order_confirmation_photos.exists())
        self.assertEqual(concatenated_order.confirmation_comment, 'Comment')

        for order in concatenated_order.orders.all():
            if order.status != OrderStatus.FAILED:
                self.assertTrue(bool(order.confirmation_signature))
                self.assertTrue(order.order_confirmation_photos.exists())
                self.assertEqual(order.confirmation_comment, 'Comment')
            else:
                self.assertFalse(bool(order.confirmation_signature))
                self.assertFalse(order.order_confirmation_photos.exists())
                self.assertNotEqual(order.confirmation_comment, 'Comment')

        self.assertTrue(concatenated_order.changed_in_offline)
        for order in concatenated_order.orders.all():
            if order.status != OrderStatus.FAILED:
                self.assertTrue(order.changed_in_offline)
            else:
                self.assertFalse(order.changed_in_offline)

        resp = self.client.patch(co_path, data={'status': OrderStatus.WAY_BACK})
        concatenated_order.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # testing way back
        exists_e_ids = list(events_qs.values_list('id', flat=True))
        resp = self.client.patch(co_path, data={
            'status': 'way_back',
            'completion': {'code_ids': [201]},
            'wayback_point': {
                'address': 'Praspiekt Pieramožcaŭ, Minsk, Belarus 312',
                'location': {
                    'lat': 53.91254758887667,
                    'lng': 27.543441765010357,
                },
            },
        })
        events = events_qs.exclude(id__in=exists_e_ids)
        self.assertEqual(events.count(), 3)
        concatenated_order.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(concatenated_order.status, Order.WAY_BACK)
        self.assertTrue(concatenated_order.terminate_codes.all().exists())
        for order in concatenated_order.orders.all():
            if order.status != OrderStatus.FAILED:
                self.assertEqual(order.status, Order.WAY_BACK)
                self.assertTrue(order.terminate_codes.all().exists())
            else:
                self.assertNotEqual(order.status, Order.WAY_BACK)
                self.assertFalse(order.terminate_codes.all().exists())

        # testing delivered
        resp = self.client.patch(co_path, data={'status': OrderStatus.DELIVERED})
        concatenated_order.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(concatenated_order.status, OrderStatus.DELIVERED)
        for order in concatenated_order.orders.all():
            if order.status != OrderStatus.FAILED:
                self.assertEqual(order.status, Order.DELIVERED)

        resp = self.client.patch(co_path, data={
            'ending_point': {
                'address': 'Fake address',
                'location': {
                    'lat': 55.5,
                    'lng': 27.5,
                },
            },
        })
        concatenated_order.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(concatenated_order.ending_point.address, 'Fake address')

        # testing documents
        image_7 = self._generate_image()
        exists_e_ids = list(events_qs.values_list('id', flat=True))
        response = self.client.patch(
            co_path + 'upload_confirmation_document/',
            data={
                'document': image_7,
                'name': 'bla',
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        events = events_qs.exclude(id__in=exists_e_ids)
        self.assertEqual(events.count(), 3)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_minimal_workflow_order(self):
        self.merchant.driver_can_create_job = True
        self.merchant.in_app_jobs_assignment = True
        self.merchant.enable_concatenated_orders = True
        self.merchant.advanced_completion = self.merchant.ADVANCED_COMPLETION_DISABLED
        self.merchant.use_subbranding = False
        self.merchant.enable_labels = False
        self.merchant.option_barcodes = self.merchant.TYPES_BARCODES.disable
        self.merchant.enable_skill_sets = False
        self.merchant.use_pick_up_status = False
        self.merchant.enable_delivery_pre_confirmation = False
        self.merchant.enable_delivery_confirmation = False
        self.merchant.enable_pick_up_confirmation = False
        self.merchant.use_way_back_status = False
        self.merchant.enable_job_description = False
        self.merchant.enable_skids = False
        self.merchant.save()

        self.client.force_authenticate(self.driver)
        path = '/api/mobile/orders/v1/'

        resp = self.client.post(path, data=self.job_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        resp = self.client.post(path, data=self.job_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).last()
        self.assertIsNotNone(concatenated_order)

        self.merchant.driver_can_create_job = False
        self.merchant.save()

        co_path = f'/api/mobile/concatenated_orders/v1/{concatenated_order.id}/'

        resp = self.client.patch(co_path, data={'status': OrderStatus.ASSIGNED, 'driver_id': self.driver.id})
        concatenated_order.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(concatenated_order.status, OrderStatus.ASSIGNED)

        resp = self.client.patch(
            co_path, data={'status': OrderStatus.IN_PROGRESS, 'offline_happened_at': timezone.now().timestamp()}
        )
        concatenated_order.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(concatenated_order.status, OrderStatus.IN_PROGRESS)

        self.assertTrue(concatenated_order.changed_in_offline)
        for order in concatenated_order.orders.all():
            self.assertTrue(order.changed_in_offline)

        resp = self.client.patch(co_path, data={'status': OrderStatus.DELIVERED})
        concatenated_order.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(concatenated_order.status, OrderStatus.DELIVERED)

    def test_concatenated_order_failed(self):
        self.merchant.enable_concatenated_orders = True
        self.merchant.advanced_completion = self.merchant.ADVANCED_COMPLETION_REQUIRED
        self.merchant.driver_can_create_job = True
        self.merchant.option_barcodes = self.merchant.TYPES_BARCODES.both
        self.merchant.use_pick_up_status = True
        self.merchant.in_app_jobs_assignment = True
        self.merchant.enable_delivery_pre_confirmation = True
        self.merchant.enable_delivery_confirmation = True
        self.merchant.enable_pick_up_confirmation = True
        self.merchant.use_way_back_status = True
        self.merchant.enable_job_description = True
        self.merchant.checklist = self.checklist
        self.merchant.save()

        self.client.force_authenticate(self.driver)
        path = '/api/mobile/orders/v1/'
        resp = self.client.post(path, data=self.job_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        resp = self.client.post(path, data=self.job_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        concatenated_order = ConcatenatedOrder.objects.filter(merchant=self.merchant).last()
        self.assertIsNotNone(concatenated_order)
        self.assertEqual(concatenated_order.status, Order.NOT_ASSIGNED)
        co_path = f'/api/mobile/concatenated_orders/v1/{concatenated_order.id}/'

        resp = self.client.get(co_path)
        self.assertTrue('customer' in resp.data)

        resp = self.client.patch(co_path, data={'status': OrderStatus.ASSIGNED, 'driver_id': self.driver.id})
        concatenated_order.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(concatenated_order.status, OrderStatus.ASSIGNED)

        resp = self.client.patch(co_path, data={'status': OrderStatus.PICK_UP})
        concatenated_order.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(concatenated_order.status, OrderStatus.PICK_UP)

        resp = self.client.patch(co_path, data={'status': OrderStatus.IN_PROGRESS})
        concatenated_order.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(concatenated_order.status, OrderStatus.IN_PROGRESS)

        with mock.patch('tasks.models.orders.Order.notify_customer') as mock_notify:
            resp = self.client.patch(co_path, data={
                'status': OrderStatus.FAILED,
                'completion': {'code_ids': [501]}
            })
            concatenated_order.refresh_from_db()
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertEqual(concatenated_order.status, OrderStatus.FAILED)
            self.assertTrue(concatenated_order.terminate_codes.all().exists())
            for order in concatenated_order.orders.all():
                self.assertEqual(order.status, Order.FAILED)
                self.assertTrue(order.terminate_codes.all().exists())
            mock_notify.assert_called_once()

        image_1 = self._generate_image()
        image_2 = self._generate_image()
        image_3 = self._generate_image()
        image_4 = self._generate_image()
        image_5 = self._generate_image()
        image_6 = self._generate_image()
        resp = self.client.patch(
            co_path + 'upload_images/',
            data={
                'pre_confirmation_signature': image_1,
                'pre_confirmation_photos': image_2,
                'pre_confirmation_comment': 'Pre comment',
                'confirmation_signature': image_3,
                'confirmation_photos': image_4,
                'confirmation_comment': 'Comment',
                'pick_up_confirmation_signature': image_5,
                'pick_up_confirmation_photos': image_6,
                'pick_up_confirmation_comment': 'Pick up comment',
                'offline_happened_at': timezone.now().timestamp(),
            },
            format='multipart',
        )
        concatenated_order.refresh_from_db()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        self.assertNotEqual(concatenated_order.pre_confirmation_signature, None)
        self.assertTrue(concatenated_order.pre_confirmation_photos.exists())
        self.assertEqual(concatenated_order.pre_confirmation_comment, 'Pre comment')

        for order in concatenated_order.orders.all():
            self.assertNotEqual(order.pre_confirmation_signature, None)
            self.assertTrue(order.pre_confirmation_photos.exists())
            self.assertEqual(order.pre_confirmation_comment, 'Pre comment')

        self.assertNotEqual(concatenated_order.confirmation_signature, None)
        self.assertTrue(concatenated_order.order_confirmation_photos.exists())
        self.assertEqual(concatenated_order.confirmation_comment, 'Comment')

        for order in concatenated_order.orders.all():
            self.assertNotEqual(order.confirmation_signature, None)
            self.assertTrue(order.order_confirmation_photos.exists())
            self.assertEqual(order.confirmation_comment, 'Comment')

        self.assertNotEqual(concatenated_order.pick_up_confirmation_signature, None)
        self.assertTrue(concatenated_order.pick_up_confirmation_photos.exists())
        self.assertEqual(concatenated_order.pick_up_confirmation_comment, 'Pick up comment')

        for order in concatenated_order.orders.all():
            self.assertNotEqual(order.pick_up_confirmation_signature, None)
            self.assertTrue(order.pick_up_confirmation_photos.exists())
            self.assertEqual(order.pick_up_confirmation_comment, 'Pick up comment')
