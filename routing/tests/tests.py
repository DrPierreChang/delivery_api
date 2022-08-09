from django.test import TestCase

from routing.utils import nearest_point_on_line_segment


class RoutingUtilsTestCase(TestCase):
    def test_nearest_point_on_segment(self):
        a = (0, 0)
        b = (4, 0)

        def assert_nearest_point(point, expected_point):
            x = nearest_point_on_line_segment(a, b, point)
            self.assertEqual(tuple(x), expected_point)

        assert_nearest_point((2, 2), (2., 0.))
        assert_nearest_point((2, 1), (2., 0.))
        assert_nearest_point((2, -2), (2., 0.))

        assert_nearest_point((5, 1), (4., 0.))
        assert_nearest_point((5, 0), (4., 0.))
        assert_nearest_point((4, 1), (4., 0.))
        assert_nearest_point((5, -2), (4., 0.))
        assert_nearest_point((4, -2), (4., 0.))

        assert_nearest_point((-1, 1), (0., 0.))
        assert_nearest_point((-1, 0), (0., 0.))
        assert_nearest_point((0, 1), (0., 0.))
        assert_nearest_point((-1, -2), (0., 0.))
        assert_nearest_point((0, -2), (0., 0.))
