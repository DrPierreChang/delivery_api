from tasks.mixins.order_status import OrderStatus


class HelperStrategy(object):
    def __init__(self):
        pass

    def get_nearest_order(self, builder_obj):
        pass

    def get_locations(self, builder_obj):
        pass

    def should_improve(self, builder_obj):
        pass

    def log_bad_route_info(self, expected_route, problem_type, **kwargs):
        pass

    def log_improved_location(self, val):
        pass


class BasicHelper(HelperStrategy):
    def __init__(self, coordinate_id):
        super(BasicHelper, self).__init__()
        self.coordinate_id = coordinate_id

    def get_nearest_order(self, builder_obj):
        return builder_obj.driver.order_set.all().filter(status=OrderStatus.IN_PROGRESS) \
            .order_by_distance(*builder_obj.last_locations[-1].location.split(',')) \
            .first()

    def get_locations(self, builder_obj):
        return list(builder_obj.driver.location.order_by('-created_at')
                    .filter(id__lte=self.coordinate_id)[:builder_obj.WINDOW_SIZE])

    def should_improve(self, builder_obj):
        return builder_obj.prev_location and builder_obj.driver.should_improve_location


class BuilderSimulatorHelper(HelperStrategy):
    def __init__(self, order, last_locations):
        super(BuilderSimulatorHelper, self).__init__()
        self.last_locations = last_locations
        self.order = order
        self.bad_route_info = None
        self.improved_location = None

    def get_nearest_order(self, builder_obj):
        return self.order

    def get_locations(self, builder_obj):
        return list(reversed(self.last_locations))[:builder_obj.WINDOW_SIZE]

    def should_improve(self, builder_obj):
        return True

    def log_bad_route_info(self, expected_route, problem_type, max_allowed_distance=None):
        if problem_type == 'ordering':
            re_build_reason = 'Ordering: %s > %s' % (expected_route.valid_prev_point_info.segment_index,
                                                     expected_route.valid_point_info.segment_index)
            additional_data = {
                'prev_expected_point': {
                    'distance_to_route': expected_route.valid_prev_point_info.distance_to_route,
                    'location': expected_route.valid_prev_point_info.location,
                    'segment_index': expected_route.valid_prev_point_info.segment_index,
                },
            }
        elif problem_type == 'distance':
            re_build_reason = 'Distance: %s > %s' % (expected_route.valid_point_info.distance_to_route,
                                                     max_allowed_distance)
            additional_data = {
                'max_allowed_distance': max_allowed_distance,
            }
        else:
            self.bad_route_info = {
                're_build_reason': 'Empty route'
            }
            return

        self.bad_route_info = {
            'type': problem_type,
            'expected_route': expected_route.route,
            'expected_point': {
                'distance_to_route': expected_route.valid_point_info.distance_to_route,
                'location': expected_route.valid_point_info.location,
                'segment_index': expected_route.valid_point_info.segment_index,
            },
            're_build_reason': re_build_reason
        }
        self.bad_route_info.update(**additional_data)

    def log_improved_location(self, val):
        self.improved_location = val
