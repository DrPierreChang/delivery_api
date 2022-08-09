from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render

import sentry_sdk
from djangosaml2.cache import OutstandingQueriesCache
from djangosaml2.conf import get_config
from djangosaml2.exceptions import IdPConfigurationMissing
from djangosaml2.overrides import Saml2Client
from djangosaml2.utils import available_idps, get_location
from djangosaml2.views import get_namespace_prefixes
from saml2 import BINDING_HTTP_REDIRECT
from saml2.mdstore import SourceNotFound

from radaro_utils.views import CustomHttpResponseRedirect


def create_saml_login_request(request):
    next_path = getattr(settings, 'LOGIN_REDIRECT_URL', None)

    try:
        conf = get_config(request=request)
    except SourceNotFound:
        msg = 'Error, IdP EntityID was not found in metadata: {}'
        return HttpResponse(msg.format('Please contact technical support.'), status=500)

    configured_idps = available_idps(conf)
    selected_idp = request.GET.get('idp', None)

    if not configured_idps:
        raise IdPConfigurationMissing('IdP configuration is missing or its metadata is expired.')
    
    if selected_idp is None:
        selected_idp = list(configured_idps.keys())[0]

    sign_requests = getattr(conf, '_sp_authn_requests_signed', False)

    client = Saml2Client(conf)

    kwargs = {}
    if getattr(conf, '_sp_force_authn', False):
        kwargs['force_authn'] = "true"
    if getattr(conf, '_sp_allow_create', False):
        kwargs['allow_create'] = "true"

    try:
        nsprefix = get_namespace_prefixes()
        session_id, result = client.prepare_for_authenticate(
            entityid=selected_idp, binding=BINDING_HTTP_REDIRECT,
            sign=sign_requests, nsprefix=nsprefix,
            **kwargs)
    except TypeError as e:
        return HttpResponse(str(e))
    else:
        http_response = CustomHttpResponseRedirect(get_location(result))

    oq_cache = OutstandingQueriesCache(request.saml_session)
    oq_cache.set(session_id, next_path)
    return http_response


def on_fail(request, exception, status, **kwargs):
    sentry_sdk.capture_exception(exception)
    return render(request, 'custom_auth/saml2/login_fail.html', status=status)
