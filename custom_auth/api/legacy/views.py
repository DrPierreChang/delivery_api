from __future__ import absolute_import, unicode_literals

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.utils.encoding import force_text
from django.utils.http import urlsafe_base64_decode
from django.views.decorators.cache import never_cache


@never_cache
def account_confirm(request, uidb64=None, token=None,
                           template_name='custom_auth/account_confirm.html',
                           token_generator=default_token_generator,
                           current_app=None, extra_context=None):

    UserModel = get_user_model()
    assert uidb64 is not None and token is not None  # checked by URLconf
    try:
        # urlsafe_base64_decode() decodes to bytestring on Python 3
        uid = force_text(urlsafe_base64_decode(uidb64))
        user = UserModel._default_manager.get(pk=uid)
    except (TypeError, ValueError, OverflowError, UserModel.DoesNotExist):
        user = None

    if user is not None and token_generator.check_token(user, token):
        user.is_confirmed = True
        user.save(update_fields=['is_confirmed'])
        return redirect(settings.FRONTEND_URL)
    context = {
        'title': 'Account confirmed unsuccessfully',
        'validlink': False,
    }

    if extra_context is not None:
        context.update(extra_context)

    if current_app is not None:
        request.current_app = current_app

    return TemplateResponse(request, template_name, context)
