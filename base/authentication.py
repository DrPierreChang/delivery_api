from django.db.models import Q

from .models import Member


class PhoneOrEmailBackend(object):
    def _try_username(self, username):
        return Member.objects.select_related(None).get(Q(username=username) | Q(email=username) | Q(phone=username))

    def authenticate(self, request, username=None, password=None, **kwargs):
        try:
            # New way of logging through email only
            # Nothing was changed to keep temporally compatibility with old style logging through phone
            # In case of multiple phone registration, logging through phone becomes impossible due to exception
            user = self._try_username(username)
            if user.check_password(password):
                return user
        except Member.DoesNotExist:
            return None
        except:
            return None

    def get_user(self, user_id):
        try:
            return Member.objects.select_related(None).get(pk=user_id)
        except Member.DoesNotExist:
            return None


class UserNameOrEmailBackend(PhoneOrEmailBackend):
    def _try_username(self, username):
        return Member.objects.select_related(None).get(Q(username=username) | Q(email=username))
