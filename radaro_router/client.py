from radaro_router.api import RadaroRouterApi


class RadaroRouterClient(object):

    def __init__(self, token):
        self._token = token
        self._api = RadaroRouterApi(token)

    def _api_request(self, http_method, method_name, **kwargs):
        return self._api.make_call(http_method, method_name, **kwargs)

    def create_member(self, data):
        return self._api_request('post', 'users', data=data)

    def create_invite(self, data):
        return self._api_request('post', 'invites', data=data)

    def check_member_data(self, query_params):
        return self._api_request('get', 'users/check', query_params=query_params)

    def check_invite_data(self, query_params):
        return self._api_request('get', 'invites/check', query_params=query_params)

    def update_member(self, member_id, data):
        return self._api_request('patch', 'users/{pk}'.format(pk=member_id), data=data)

    def update_invite(self, invite_id, data):
        return self._api_request('patch', 'invites/{pk}'.format(pk=invite_id), data=data)

    def delete_member(self, member_id):
        return self._api_request('delete', 'users/{pk}'.format(pk=member_id))

    def delete_invite(self, invite_id):
        return self._api_request('delete', 'invites/{pk}'.format(pk=invite_id))

    def get_login_route(self, username):
        return self._api_request('post', 'router/login', data={'username': username})

    def get_invite_route(self, phone):
        return self._api_request('post', 'router/register', data={'phone': phone})

    def deactivate_member(self, member_id):
        return self._api_request('put', 'users/{pk}/deactivate'.format(pk=member_id))

    def deactivate_invite(self, invite_id):
        return self._api_request('put', 'invites/{pk}/deactivate'.format(pk=invite_id))

    def activate_member(self, member_id):
        return self._api_request('put', 'users/{pk}/activate'.format(pk=member_id))

    def activate_invite(self, invite_id):
        return self._api_request('put', 'invites/{pk}/activate'.format(pk=invite_id))
