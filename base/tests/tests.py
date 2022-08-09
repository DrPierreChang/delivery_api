from __future__ import absolute_import, unicode_literals

from django.conf import settings
from django.contrib.auth.forms import UserChangeForm
from django.forms import modelform_factory
from django.test import TestCase

import mock

from base.factories import MemberFactory
from base.models import Member
from driver.utils import WorkStatus
from merchant.factories import MerchantFactory


class PhoneNumbersAdminTestCase(TestCase):
    def test_add_member_admin(self):
        from django.contrib.admin import site

        from base.admin import MemberAdmin

        class MockRequest(object):
            def __init__(self, user=None):
                self.user = user
                self.version = settings.LATEST_API_VERSION

        super_user = Member.objects.create_superuser(email='super@email.org', password='pass')
        member_admin = MemberAdmin(model=Member, admin_site=site)
        request = MockRequest(user=super_user)
        phones = ['1234', '7788', '2025550174', '202-555-0174', '+202-555-0174', '+375299876745']
        with mock.patch('crequest.middleware.CrequestMiddleware.get_request', return_value=request):
            for i, phone in enumerate(phones):
                email = 's{}@s.com'.format(i)
                ChangeForm = modelform_factory(Member, form=UserChangeForm, exclude=('merchant',))
                obj = Member.objects.create(phone='1111', email=email, username=email)
                obj.phone = phone
                form = ChangeForm({'phone': phone}, instance=obj)
                form.is_valid()
                member_admin.save_model(obj=obj, request=request, form=form, change=None)
                self.assertTrue(Member.objects.filter(phone=phone).exists())


class MemberTestCase(TestCase):

    def test_is_active_member(self):
        member = MemberFactory(merchant=MerchantFactory(), work_status=WorkStatus.WORKING, is_active=True)
        member.is_active = False
        member.save()
        member.refresh_from_db()

        self.assertFalse(member.is_active)
