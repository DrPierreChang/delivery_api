from __future__ import absolute_import, unicode_literals

import abc
import copy
import json
import os
from base64 import b64encode

from django.conf import settings
from django.utils import timezone

from rest_framework.status import HTTP_200_OK, HTTP_201_CREATED, HTTP_204_NO_CONTENT

import gpxpy
import gpxpy.gpx
import requests

from driver.utils import WorkStatus
from testing.settings import ACCURACY, SPEED


class ClientException(Exception):
    def __init__(self, *args, **kwargs):
        self.resp = kwargs.pop('resp') if kwargs.get('resp') else None
        super(ClientException, self).__init__(self, *args)


class Client(metaclass=abc.ABCMeta):
    urls = None
    role = None

    def __init__(self, env):
        from testing.status import STATUS

        from . import envs

        self.STATUS = STATUS

        self.env_name = env
        self.env = getattr(envs, env).SETTINGS
        self.token_file_name = settings.BASE_DIR + '/testing/token-{}-{}'.format(self.role, self.env_name)
        if not self.urls or not self.urls.get('login'):
            raise ClientException('No url object or login url were provided.')
        if not self.role:
            raise ClientException('Client\'s role wasn\'t provided.')
        self.urls.update({
            'driver_api': '/api/drivers',
            'order_api': '/api/orders',
            'me': '/api/users/me',
            'logout': '/api/auth/logout'
        })
        self.headers = {}
        self.settings = self.env[self.role]
        self.login()

    def _send(self, route, method, answers=(HTTP_200_OK,), **kwargs):
        print('[{}] {}'.format(timezone.now(), route))
        resp = getattr(requests, method)(url=self.env['url'] + route, headers=self.headers, **kwargs)
        try:
            _json = resp.json()
        except Exception as ex:
            _json = None
        if resp.status_code not in answers:
            raise ClientException('{}: {} ({})'.format(resp.status_code, resp.reason, resp.content), resp=_json)
        return resp

    def _get(self, route, **kwargs):
        return self._send(route, 'get', **kwargs)

    def _delete(self, route):
        return self._send(route, 'delete', answers=(HTTP_204_NO_CONTENT,))

    def _post(self, route, json):
        return self._send(route, 'post', answers=(HTTP_200_OK, HTTP_201_CREATED), json=json)

    def _put(self, route, json):
        return self._send(route, 'put', answers=(HTTP_200_OK, HTTP_201_CREATED), json=json)

    def _patch(self, route, json):
        return self._send(route, 'patch', answers=(HTTP_200_OK, HTTP_201_CREATED), json=json)

    def login(self):
        print('Login...')
        try:
            with open(self.token_file_name, 'rt') as f:
                self.headers.update({'Authorization': f.read()})
        except IOError as ie:
            resp = self._post(self.urls['login'],
                              {'username': self.settings['login'], 'password': self.settings['password']})
            token_header = 'Token ' + resp.headers['X-Token']
            self.headers.update({'Authorization': token_header})
            with open(self.token_file_name, 'wt') as f:
                f.write(token_header)

        resp = self._get(self.urls['me'])
        self.me = resp.json()
        print('Ready. You are: {} {} {}.'.format(self.role, self.me['first_name'], self.me['last_name']))

    def logout(self):
        if self.headers.get('Authorization'):
            self._delete(self.urls['logout'])
            del self.headers['Authorization']
            os.remove(self.token_file_name)

    def __del__(self):
        self.logout()


class DriverClient(Client):
    tracks = {}
    job = None
    role = 'driver'
    urls = {
        'login': '/api/auth/login-driver?force=True'
    }

    def __init__(self, env):
        super(DriverClient, self).__init__(env)
        self.track_path = settings.BASE_DIR + '/testing/tracks/'
        self.dump_path = settings.BASE_DIR + '/testing/dumps/'
        self._put('{}/me/status/'.format(self.urls['driver_api'], self.me['id']), {'work_status': WorkStatus.WORKING})
        if not os.path.exists(self.track_path):
            os.mkdir(self.track_path)

    def create_track_from_dump(self, dump):
        gpx = gpxpy.gpx.GPX()

        # Create first track in our GPX:
        gpx_track = gpxpy.gpx.GPXTrack()
        gpx.tracks.append(gpx_track)

        # Create first segment in our GPX track:
        gpx_segment = gpxpy.gpx.GPXTrackSegment()
        gpx_track.segments.append(gpx_segment)
        for pnt in dump:
            point = gpxpy.gpx.GPXTrackPoint(
                *list(map(float, pnt['location'].split(','))),
                speed=pnt['speed'],
                time=timezone.datetime.utcfromtimestamp(pnt['timestamp'])
            )
            point.accuracy = pnt['accuracy']
            point.bearing = pnt.get('bearing', 0.0)
            gpx_segment.points.append(point)
        return gpx

    def load_track(self, name, idx=None):
        if not self.tracks.get(name):
            split_name = name.split('.')
            track_name = settings.BASE_DIR + '/testing/{}.{}'.format('.'.join(split_name[:-1]), split_name[-1])
            if os.path.exists(track_name):
                with open(track_name, 'r') as track_file:
                    if split_name[-1].lower() == 'gpx':
                        self.tracks[name] = gpxpy.parse(track_file).tracks[0]
                    elif split_name[-1].lower() == 'json':
                        dump_data = json.loads(track_file.read())
                        points = dump_data[idx] if idx is not None else dump_data
                        self.tracks[name] = self.create_track_from_dump(points).tracks[0]
                    else:
                        raise ClientException('No accessible format provided.')
                    print('{} loaded.'.format(name))
                    if idx is not None:
                        print('Loaded path with index %s' % idx)
            else:
                print('{} not found.'.format(name))
        return self.tracks[name]

    def set_position(self, *args, **kwargs):
        self._post('{}/me/locations'.format(self.urls['driver_api']),
                   {'location': '{},{}'.format(*args),
                    'accuracy': kwargs.get('accuracy', ACCURACY),
                    'speed': kwargs.get('speed', SPEED),
                    'bearing': kwargs.get('bearing', 0.0),
                    })

    def set_geofence(self, val, status=None):
        params = {'geofence_entered': val}
        if status:
            params['status'] = status
        self._put('{}/{}/geofence/'.format(self.urls['order_api'], self.job['order_id']), params)
        print('Geofence set to: {}'.format(val))

    def set_status(self, val, add=None):
        req = {'status': val}
        if add:
            req.update(add)
        self._put('{}/{}/status/'.format(self.urls['order_api'], self.job['order_id']), req)
        print('Status set to: {}'.format(val))

    def commit_job(self, track):
        point = track.segments[0].points[-1]
        self.set_position(point.latitude, point.longitude)
        if self.me['merchant']['allow_confirmation']:
            with open('testing/assets/confirm.png', 'rb') as f:
                add = {'confirmation_photo': {"image": b64encode(f.read())}}
        else:
            add = None
        self.set_status(self.STATUS.DELIVERED, add)

    def get_jobs(self, **kwargs):
        jobs = []
        page = 1
        while True:
            resp = self._get(route='/api/orders/', params={'page_size': 9999, 'page': page}).json()
            jobs += resp['results']
            if resp['next']:
                page += 1
            else:
                break
        if kwargs:
            return [job for job in jobs for f in list(kwargs.keys()) if job[f] == kwargs[f]]
        else:
            return jobs

    def accept_job(self, job_id):
        resp = self._get('{}/{}/'.format(self.urls['order_api'], job_id))
        self.job = resp.json()
        if self.job and self.job['status'] != self.STATUS.ASSIGNED:
            raise ClientException('Accepting job is failed. Status is not {}'.format(self.STATUS.ASSIGNED))

    def logout(self):
        self._put('{}/me/status/'.format(self.urls['driver_api'], self.me['id']), {'work_status': WorkStatus.NOT_WORKING})
        super(DriverClient, self).logout()


class MerchantClient(Client):
    role = 'manager'
    urls = {
        'login': '/api/auth/login-merchant'
    }

    def __init__(self, env):
        super(MerchantClient, self).__init__(env)

    def create_job(self, job_params=None):
        job = copy.copy(self.settings['default_job'])
        if job_params:
            job.update(job_params)
        resp = self._post(self.urls['order_api'], job)
        _job = resp.json()
        return _job

    def delete_job(self, job_id):
        self._delete('{}/{}'.format(self.urls['order_api'], job_id))

    def assign_job(self, job_id, driver_id=None):
        self._patch('{}/{}'.format(self.urls['order_api'], job_id),
                    {'driver': driver_id or self.settings['default_driver'], 'status': 'assigned'})
