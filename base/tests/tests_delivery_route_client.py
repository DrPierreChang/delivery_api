from django.db import transaction
from django.test import override_settings

from rest_framework import status
from rest_framework.test import APITestCase

from mock import mock, patch

from base.factories import DriverFactory, InviteFactory, ManagerFactory
from base.models import Invite, Member
from merchant.factories import MerchantFactory


@override_settings(TESTING_MODE=False)
class RadaroRouterClientTestCase(APITestCase):
    fixtures = ['fixtures/tests/constance.json', ]

    def run_commit_hooks(self):
        """
        Fake transaction commit to run delayed on_commit functions
        :return:
        """
        for db_name in reversed(self._databases_names()):
            with mock.patch('django.db.backends.base.base.BaseDatabaseWrapper.validate_no_atomic_block',
                            lambda a: False):
                transaction.get_connection(using=db_name).run_and_clear_commit_hooks()

    @classmethod
    def setUpTestData(cls):
        super(RadaroRouterClientTestCase, cls).setUpTestData()
        cls.merchant = MerchantFactory()
        with patch('radaro_router.client.RadaroRouterClient.create_member') as mock_create:
            mock_create.return_value = {"id": 1}
            cls.manager = ManagerFactory(merchant=cls.merchant)
        cls.invite_user_info = {
            "phone": "+61499999990",
            "email": "new_driver@gm.co",
            "first_name": "Testdriver"
        }

    @patch('radaro_router.client.RadaroRouterClient.create_invite', return_value={"id": 1})
    @patch('radaro_router.client.RadaroRouterClient.create_member', return_value={"id": 1})
    def setUp(self, create_member_patch, create_invite_patch):
        super(RadaroRouterClientTestCase, self).setUp()
        self.member = DriverFactory(merchant=self.merchant)
        self.invite = InviteFactory(initiator=self.manager, merchant=self.merchant)
        self.run_commit_hooks()
        self.assertTrue(create_member_patch.called)

    def tearDown(self):
        super(RadaroRouterClientTestCase, self).tearDown()
        with patch('radaro_router.client.RadaroRouterClient.delete_invite') as mock_delete:
            mock_delete.return_value = {}
            Invite.objects.all().delete()

    @patch('radaro_router.client.RadaroRouterClient.create_member', return_value={"id": 1})
    def test_member_creation(self, create_member_patch):
        member = DriverFactory(merchant=self.merchant)
        self.run_commit_hooks()
        self.assertTrue(create_member_patch.called)
        member = Member.objects.get(id=member.id)
        self.assertEqual(member.radaro_router.remote_id, create_member_patch.return_value['id'])

    @patch('radaro_router.client.RadaroRouterClient.create_invite', return_value={"id": 1})
    def test_invite_creation(self,  create_invite_patch):
        self.client.force_authenticate(self.manager)
        resp = self.client.post('/api/invitations/', self.invite_user_info)
        self.run_commit_hooks()
        self.assertTrue(create_invite_patch.called)
        self.assertTrue(Invite.objects.filter(pk=resp.data['id']).exists())
        invite = Invite.objects.get(id=resp.data['id'])
        self.assertEqual(invite.radaro_router.remote_id, create_invite_patch.return_value['id'])
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

    @patch('radaro_router.client.RadaroRouterClient.update_member')
    def test_member_update(self, update_member_patch):
        old_username, old_email = self.member.username, self.member.email
        self.member.username = "test"
        self.member.email = "test@test.com"
        self.member.save(update_fields=('username', 'email'))
        self.run_commit_hooks()
        self.assertTrue(update_member_patch.called)

        self.member.refresh_from_db()
        self.assertNotEqual(old_username, self.member.username)
        self.assertNotEqual(old_email, self.member.email)

    @patch('radaro_router.client.RadaroRouterClient.update_invite')
    def test_invite_update(self, update_invite_patch):
        old_email = self.invite.email
        self.invite.email = "test@test.com"
        self.invite.save(update_fields=('email', ))
        self.run_commit_hooks()
        self.assertTrue(update_invite_patch.called)

        self.invite.refresh_from_db()
        self.assertNotEqual(self.invite.email, old_email)

    @patch('radaro_router.client.RadaroRouterClient.delete_member')
    def test_member_delete(self, delete_member_patch):
        self.member.delete()
        self.run_commit_hooks()
        self.assertTrue(delete_member_patch.called)
        self.assertFalse(Member.objects.filter(id=self.member.id).exists())

    @patch('radaro_router.client.RadaroRouterClient.delete_invite')
    def test_invite_delete(self, delete_invite_patch):
        self.invite.delete()
        self.run_commit_hooks()
        self.assertTrue(delete_invite_patch.called)
        self.assertFalse(Invite.objects.filter(id=self.invite.id).exists())
