from __future__ import unicode_literals

import json
import time

import geopy
import requests

from routing.utils import dump_track
from testing.client import ClientException, DriverClient, MerchantClient
from testing.settings import TESTING_DIR, TIMEOUT


class Path(object):
    MATCH = 'http://0.0.0.0:5000/match/v1/car/'

    def __init__(self, str_json_name):
        str_path = TESTING_DIR + '/dumps/{}.json'.format(str_json_name)
        with open(str_path, 'rt') as json_file:
            str_json = json_file.read()
            self.locs = json.loads(str_json)

    def filter_path(self, verbose=0):
        points_str = ';'.join([','.join(reversed(i['location'].split(','))) for i in self.locs])
        radius_str = ';'.join([str(i['accuracy']) for i in self.locs])
        timestamp_str = ';'.join([str(i['created_at']) for i in self.locs])
        try:
            a_test = requests.get(self.MATCH + '{}?overview=full&geometries=geojson&steps=true&radiuses={}&timestamps={}'.format(points_str, radius_str, timestamp_str))
            pnt_x = a_test.json()['matchings'][0]['geometry']['coordinates']
            return pnt_x, a_test.json()
        except Exception as ex:
            print(ex.__dict__)
            print(a_test.json() if a_test else None)
            raise ex

    def dump_path(self, name):
        dump_track('.', name, self.path)

    def dump_locs(self, name):
        dump_track('.', name, self.locs)


class Tester(object):
    jobs = {}

    def __init__(self, env):
        self.driver = DriverClient(env)
        self.manager = MerchantClient(env)

    def _run_path(self, gpx, timeout):
        point = gpx.segments[0].points[0]
        self.driver.set_position(point.latitude, point.longitude)
        self.driver.set_status(self.driver.STATUS.IN_PROGRESS)
        if timeout:
            time.sleep(timeout)
            for segment in gpx.segments:
                for point in segment.points:
                    self.driver.set_position(point.latitude, point.longitude, accuracy=point.accuracy,
                                             speed=point.speed, bearing=point.bearing)
                    time.sleep(timeout)
        else:
            threshold = 0.2
            for segment in gpx.segments:
                now_point = segment.points[0]
                for point in segment.points[1:]:
                    self.driver.set_position(point.latitude, point.longitude, accuracy=point.accuracy,
                                             speed=point.speed, bearing=point.bearing)
                    wait_time = (point.time - now_point.time).total_seconds() - threshold
                    if wait_time > 0:
                        time.sleep(wait_time)
                    now_point = point

    def _prepare_job(self, gpx, **kwargs):
        point = gpx.segments[0].points[-1]
        location = '{},{}'.format(point.latitude, point.longitude)
        if not kwargs.get('deliver_address'):
            try:
                point = geopy.Nominatim(user_agent='Radaro').geocode(location).address
            except:
                point = geopy.GoogleV3().geocode(location).address
            kwargs.update({
                'deliver_address': {
                    'location': location,
                    'address': point
                }
            })
        job = self.manager.create_job(job_params=kwargs)
        self.jobs[job['order_id']] = job
        self.manager.assign_job(job['order_id'])
        self.driver.accept_job(job['order_id'])
        return job

    def run_job(self, name, timeout=TIMEOUT, **kwargs):
        gpx = self.driver.load_track(name, idx=kwargs.get('path_index', None))
        self._prepare_job(gpx, **kwargs)
        self._run_path(gpx, timeout)
        self.driver.set_geofence(True)
        return gpx

    def force_online(self, name, timeout=TIMEOUT, **kwargs):
        gpx = self.driver.load_track(name)
        while True:
            for point in gpx.segments[0].points[:2]:
                self.driver.set_position(point.latitude, point.longitude)
                time.sleep(timeout)

    def run_job_and_complete(self, name, timeout=TIMEOUT, **kwargs):
        gpx = self.run_job(name, timeout, **kwargs)
        time.sleep(timeout)
        try:
            self.driver.commit_job(gpx)
        except ClientException as ce:
            if not ce.resp['errors']['status'][0] == "Order has been already marked as delivered":
                raise ce
        time.sleep(timeout)
        self.driver.set_geofence(False)

    def run_job_and_send_status_with_geofence(self, name, timeout=TIMEOUT, **kwargs):
        gpx = self.driver.load_track(name)
        self._prepare_job(gpx, **kwargs)
        self._run_path(gpx, timeout)
        self.driver.set_geofence(True, self.driver.STATUS.DELIVERED)

    def remove_jobs(self, *args, **kwargs):
        kw = {'title': 'Some test job'}
        jobs = self.driver.get_jobs(**kw)
        for job in jobs:
            self.manager.delete_job(job['order_id'])
            if self.jobs.get(job['order_id']):
                del self.jobs[job['order_id']]
        print('Deleted {} jobs.'.format(len(jobs)))

    def __del__(self):
        del self.manager
        del self.driver
