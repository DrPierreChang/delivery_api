from collections import defaultdict

from django.core.cache import cache

import googlemaps

from radaro_utils.helpers import chunks
from routing.google import GoogleClient


class ETAToOrders(object):
    gc = GoogleClient()
    ETA_STORAGE_TIME_IN_CACHE = 120  # In seconds

    @staticmethod
    def get_eta_from_cache(order):
        if order.id:
            return cache.get('order-eta-{}'.format(order.id))
        return None

    @staticmethod
    def save_eta_in_cache(order, value, seconds=ETA_STORAGE_TIME_IN_CACHE):
        if order.id:
            cache_key = 'order-eta-{}'.format(order.id)
            cache.set(cache_key, value, seconds)
        return value

    def _filter_orders(self, items):
        filtered_items = {}
        for item in items:
            # It makes no sense to count the time if the driver has not yet started, or has already delivered
            if item.status not in item.status_groups.MONITORED:
                continue

            if item.concatenated_order is not None:
                order = item.concatenated_order
            else:
                order = item

            if order.driver.last_location is None:
                continue

            start_point = order.driver.last_location.improved_location or order.driver.last_location.location
            end_point = order.deliver_address.location
            if not start_point or not end_point:
                continue

            filtered_items[order.id] = order

        return list(filtered_items.values())

    @staticmethod
    def _get_orders_requiring_calculate_eta(orders):
        # the method filters out those eta that do not need to be calculated, or can be obtained from the cache
        orders_without_eta = []
        eta_values = defaultdict(lambda: {'text': None, 'value': None})

        for order in orders:
            eta = ETAToOrders.get_eta_from_cache(order)
            if eta:
                eta_values[order.id] = eta
            else:
                orders_without_eta.append(order)

        return orders_without_eta, eta_values

    def _get_information_on_the_route_of_orders(self, orders, merchant):
        # Build a list of driver locations and their goals
        points = []
        for order in orders:
            points.append(order.driver.last_location.improved_location or order.driver.last_location.location)
            points.append(order.deliver_address.location)

        with self.gc.track_merchant(merchant):
            res = self.gc.pure_directions_request(
                origin=points[0],
                destination=points[-1],
                waypoints=points[1:-1],
                track_merchant=True,
            )
        # In addition to data on how much the driver will go to the destination,
        # there is data on how much you need to go from the goal to the next driver. The second is to filter
        return zip(orders, res[0]['legs'][::2])

    def get_eta_many_orders(self, orders, merchant):
        orders = self._filter_orders(list(orders))
        orders_without_eta, eta_values = self._get_orders_requiring_calculate_eta(orders)

        # Here the list of orders is divided into lists of 12 elements each
        segments = chunks(orders_without_eta, 12)

        for segment in segments:
            try:
                routes = self._get_information_on_the_route_of_orders(segment, merchant)
                for order, leg in routes:
                    self.save_eta_in_cache(order, leg['duration'])
                    eta_values[order.id] = leg['duration']
            except (googlemaps.exceptions.ApiError, KeyError):
                pass

        return eta_values

    @staticmethod
    def calculate_eta(order):
        driver_last_location = order.driver.last_location.improved_location or order.driver.last_location.location
        try:
            with GoogleClient.track_merchant(order.merchant):
                res = GoogleClient().single_dima_element(
                    origin=driver_last_location,
                    destination=order.deliver_address.location,
                    track_merchant=True,
                    language=order.merchant.language
                )
                ETAToOrders.save_eta_in_cache(order, res['duration'])
                return res['duration']
        except (googlemaps.exceptions.ApiError, KeyError):
            pass

    @staticmethod
    def get_eta(order):
        if not (order.driver and order.driver.last_location):
            return None
        if order.status not in order.status_groups.MONITORED:
            return None

        if order.concatenated_order is not None:
            order = order.concatenated_order

        eta = ETAToOrders.get_eta_from_cache(order)
        if eta is not None:
            return eta

        return ETAToOrders.calculate_eta(order)
