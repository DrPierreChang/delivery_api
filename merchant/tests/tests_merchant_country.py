import io

from django.contrib.auth.forms import UserChangeForm
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.forms import model_to_dict, modelform_factory

from rest_framework import status
from rest_framework.test import APITestCase

from constance.test import override_config

from base.factories import DriverFactory, ManagerFactory
from base.models import Invite, Member
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory, SkillSetFactory
from merchant.models import Merchant
from tasks.models.orders import Order
from tasks.tests.factories import CustomerFactory, OrderFactory
from tasks.tests.utils import CreateOrderCSVTextMixin


@override_config(ALLOWED_COUNTRIES=['NE', 'AU'])
class AllowedCountriesConfigTestCase(APITestCase):
    @classmethod
    def setUpClass(cls):
        super(AllowedCountriesConfigTestCase, cls).setUpClass()
        cls.niger_phone_number = "+22796293445"
        cls.niger_invalid_number = "+375448777678"

        cls.new_country, cls.wrong_country = 'NE', 'TD'

    def test_set_merchant_country(self):
        manager = ManagerFactory(work_status=WorkStatus.WORKING)
        self.client.force_authenticate(manager)

        resp = self.client.patch('/api/merchant/my/', {'countries': [self.wrong_country, ]})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        resp = self.client.patch('/api/merchant/my/', {'countries': [self.new_country, ]})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data.get('countries', []), [self.new_country, ])

    def test_change_merchant_phone_number(self):
        manager = ManagerFactory(merchant__countries=[self.new_country, ])
        self.client.force_authenticate(manager)

        resp = self.client.patch('/api/merchant/my/', {'phone': self.niger_invalid_number})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        resp = self.client.patch('/api/merchant/my/', {'phone': self.niger_phone_number})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_change_merchant_notify_skill_sets(self):
        manager = ManagerFactory(merchant__notify_of_not_assigned_orders=True)
        self.client.force_authenticate(manager)

        skill_set = SkillSetFactory(merchant=manager.merchant)
        manager.merchant.required_skill_sets_for_notify_orders.add(skill_set)

        resp = self.client.patch('/api/merchant/my/', {'required_skill_sets_for_notify_orders_ids': [skill_set.id]})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['required_skill_sets_for_notify_orders_ids'], [skill_set.id])

    def test_create_order_with_local_phone(self):
        manager = ManagerFactory(merchant__countries=[self.new_country, ])
        self.client.force_authenticate(manager)

        order_data = {
            'customer': {
                'name': 'Customer',
                'phone': self.niger_invalid_number,
            },
            'deliver_address': {
                'address': 'Sydney, AU',
                'location': '-33.874904,151.207976'
            }
        }
        resp = self.client.post('/api/orders/', order_data)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        order_data['customer']['phone'] = self.niger_phone_number
        resp = self.client.post('/api/orders/', order_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        Order.objects.get(order_id=resp.data['order_id'])


class LocalPhoneNumbersTestCase(CreateOrderCSVTextMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        super(LocalPhoneNumbersTestCase, cls).setUpTestData()
        cls.manager = ManagerFactory(merchant__countries=["AU", ], work_status=WorkStatus.WORKING)
        cls.merchant = MerchantFactory(countries=['AU', ], name='Test merchant', date_format=Merchant.LITTLE_ENDIAN)

        cls.invite_user_info = {
            "phone": None,
            "email": "driver@email.com",
        }

        cls.order_data = {
            'customer': {
                'name': 'Customer',
            },
            'deliver_address': {
                'address': 'Sydney, AU',
                'location': '-33.874904,151.207976'
            }
        }

        cls.valid_number_for_country = "+61499999990"
        cls.invalid_number_for_country = "+375448777678"

    def setUp(self):
        self.client.force_authenticate(self.manager)

    def tearDown(self):
        if hasattr(self, 'file'):
            self.file.close()

    def test_invite_driver(self):
        resp = self.client.post('/api/invitations/', dict(self.invite_user_info, phone=self.valid_number_for_country))
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Invite.objects.filter(pk=resp.data['id']).exists())

    def test_fail_invite_driver(self):
        resp = self.client.post('/api/invitations/', dict(self.invite_user_info, phone=self.invalid_number_for_country))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_manager(self):
        self.change_member_form(ManagerFactory(merchant=self.merchant, phone=self.valid_number_for_country))

    def test_create_driver(self):
        self.change_member_form(DriverFactory(merchant=self.merchant, phone=self.valid_number_for_country))

    def test_create_job_with_local_number(self):
        order_data = dict(self.order_data)
        order_data['customer']['phone'] = self.valid_number_for_country
        resp = self.client.post('/api/orders/', self.order_data)
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        Order.objects.get(order_id=resp.data['order_id'])

        order_data['customer']['phone'] = self.invalid_number_for_country
        resp = self.client.post('/api/orders/', dict(self.order_data, phone=self.invalid_number_for_country))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_success_bulk_upload(self):
        resp = self.create_orders(self.valid_number_for_country)

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotIn('errors', resp.data)

    def test_fail_bulk_upload(self):
        resp = self.create_orders(self.invalid_number_for_country)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        errors_with_phone = (resp.data['errors'])
        self.assertTrue(len(errors_with_phone) > 0)

    def change_member_form(self, member):
        valid_form_data = model_to_dict(member, exclude=('merchant',))
        invalid_form_data = dict(valid_form_data, phone=self.invalid_number_for_country)

        ChangeForm = modelform_factory(Member, form=UserChangeForm, exclude=('merchant',))
        form = ChangeForm(valid_form_data, instance=member)
        self.assertTrue(form.is_valid())

        form = ChangeForm(invalid_form_data, instance=member)
        self.assertFalse(form.is_valid())

    def create_orders(self, customer_phone):
        customer = CustomerFactory(
            phone=customer_phone,
            name='Customer'
        )
        orders_list = OrderFactory.create_batch(
            size=3,
            driver=None,
            customer=customer
        )

        csv_text = self.create_csv_text(orders_list)
        io_ = io.StringIO(csv_text)
        self.file = InMemoryUploadedFile(io_, None, 'test.csv', 'csv', None, None)
        return self.client.post('/api/bulk/', format='multipart', data={'file': self.file})
