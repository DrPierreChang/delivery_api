from typing import List
from unittest import TestCase

from route_optimisation.intelligent_clustering.merge import Coefficient


def run_coefficient_changing_path(path: list, start=None):
    coefficient_finder = Coefficient(start)
    coefficient_generator = coefficient_finder()
    for coefficient in coefficient_generator:
        yield coefficient
        if not path:
            break
        if path.pop(0):
            coefficient_finder.up_coefficient()
        else:
            coefficient_finder.down_coefficient()


class TestMergeCoefficient(TestCase):
    def assert_coefficient_changing(self, start, path: list, expected: List[float]):
        for coefficient in run_coefficient_changing_path(path, start):
            expected_coefficient = expected.pop(0)
            self.assertEqual(expected_coefficient, coefficient)
        self.assertEqual(len(expected), 0)

    def test_merge_coefficient(self):
        self.assert_coefficient_changing(start=None, path=[True, False, False], expected=[1.0, 2.0, 1.5, 1.25])
        self.assert_coefficient_changing(
            start=None, path=[True, False, True, False, True, False, True, False, True],
            expected=[1.0, 2.0, 1.5, 1.75, 1.62, 1.69, 1.66]
        )
        self.assert_coefficient_changing(
            start=None, path=[True, False, True, False, True, False, True, True],
            expected=[1.0, 2.0, 1.5, 1.75, 1.62, 1.69, 1.66]
        )
        with self.assertRaises(AssertionError):
            self.assert_coefficient_changing(
                start=None, path=[True, False, True, False, True, False, True, False, True],
                expected=[1.0, 2.0, 1.5, 1.75, 1.62, 1.69, 1.66, 1.67, 1.68]
            )
        with self.assertRaises(IndexError):
            self.assert_coefficient_changing(
                start=None, path=[True, False, True, False, True, False, True, False, True],
                expected=[1.0, 2.0, 1.5, 1.75, 1.62, 1.69]
            )

        self.assert_coefficient_changing(
            start=None, path=[True, True, True, True, True, False, True, False, True, True],
            expected=[1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 24.0, 28.0, 26.0, 27.0, 27.5]
        )
        self.assert_coefficient_changing(
            start=None, path=[True, True, True, True, True, False, True, False, True, True, False, False, False, False],
            expected=[1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 24.0, 28.0, 26.0, 27.0, 27.5, 27.25, 27.12, 27.06, 27.03]
        )
        self.assert_coefficient_changing(
            start=None, path=[True, True, True, True, True, False, True, False, True, True,
                              False, False, False, False, True, False, True, True],
            expected=[1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 24.0, 28.0, 26.0, 27.0, 27.5,
                      27.25, 27.12, 27.06, 27.03, 27.05]
        )

        self.assert_coefficient_changing(
            start=None, path=[False, False, False, False, True, True, True, True],
            expected=[1.0, 0.5, 0.25, 0.12, 0.05, 0.08, 0.1]
        )
        self.assert_coefficient_changing(
            start=None, path=[False, False, False, True, True, True],
            expected=[1.0, 0.5, 0.25, 0.12, 0.18, 0.21, 0.23]
        )

        self.assert_coefficient_changing(
            start=1.45, path=[False, False, False, False, True, True, True, True],
            expected=[1.45, 1.40, 1.35, 1.30, 1.25, 1.27, 1.29]
        )
        self.assert_coefficient_changing(
            start=1.45, path=[False, True, False, True],
            expected=[1.45, 1.40, 1.42]
        )
        self.assert_coefficient_changing(
            start=1.45, path=[True, True, True, False, False, False],
            expected=[1.45, 1.50, 1.55, 1.60, 1.58, 1.56]
        )

        self.assert_coefficient_changing(
            start=0.45, path=[False, False, False, False, True, True, True],
            expected=[0.45, 0.40, 0.35, 0.30, 0.25, 0.28]
        )
        self.assert_coefficient_changing(
            start=0.45, path=[False, True, False, True],
            expected=[0.45, 0.40, 0.43]
        )
        self.assert_coefficient_changing(
            start=0.45, path=[True, True, True, False, False],
            expected=[0.45, 0.50, 0.55, 0.60, 0.57]
        )

    def assert_can_find_coefficient(self, start, looking_for: float, expected_path: List[bool]):
        coefficient_finder = Coefficient(start)
        coefficient_generator = coefficient_finder()
        history = []
        for coefficient in coefficient_generator:
            history.append(coefficient)
            if coefficient == looking_for:
                self.assertEqual(len(expected_path), 0)
                return
            expected_next = expected_path.pop(0)
            next_is = looking_for > coefficient
            self.assertEqual(next_is, expected_next)
            if next_is:
                coefficient_finder.up_coefficient()
            else:
                coefficient_finder.down_coefficient()

        self.assertEqual(len(expected_path), 0)
        closest = list(filter(lambda x: x < looking_for, history))[-1]
        if 0 <= looking_for - closest <= 0.04:
            return
        self.fail(f'Cant find looking coefficient {looking_for}')

    def test_find_coefficient(self):
        self.assert_can_find_coefficient(start=None, looking_for=2.0, expected_path=[True])
        self.assert_can_find_coefficient(
            start=None, looking_for=2.001,
            expected_path=[True, True, False, False, False, False, False, False, False, False]
        )
        with self.assertRaises(IndexError):
            self.assert_can_find_coefficient(
                start=None, looking_for=2.001,
                expected_path=[True, True, False, False, False, False, False, False]
            )
        with self.assertRaises(AssertionError):
            self.assert_can_find_coefficient(
                start=None, looking_for=2.001,
                expected_path=[True, True, False, False, False, False, False, False, False, False, False]
            )

        self.assert_can_find_coefficient(
            start=None, looking_for=24.157,
            expected_path=[
                True, True, True, True, True, False, True, False, False, False, False, False, True, False, False, True
            ]
        )
        self.assert_can_find_coefficient(
            start=None, looking_for=24.147,
            expected_path=[
                True, True, True, True, True, False, True, False, False, False, False, False, True, False, False, True
            ]
        )
        self.assert_can_find_coefficient(
            start=None, looking_for=24.137,
            expected_path=[
                True, True, True, True, True, False, True, False, False, False, False, False, True, False, False, False
            ]
        )
        self.assert_can_find_coefficient(
            start=None, looking_for=24.127,
            expected_path=[
                True, True, True, True, True, False, True, False, False, False, False, False, True, False, False, False
            ]
        )
        self.assert_can_find_coefficient(
            start=None, looking_for=1.147,
            expected_path=[True, False, False, False, True, False, False, True]
        )
        self.assert_can_find_coefficient(
            start=None, looking_for=0.487,
            expected_path=[False, False, True, True, True, True]
        )

        self.assert_can_find_coefficient(
            start=0.5, looking_for=0.487,
            expected_path=[False, True, True]
        )
        self.assert_can_find_coefficient(
            start=0.45, looking_for=0.487,
            expected_path=[True, False, True]
        )
        self.assert_can_find_coefficient(
            start=0.65, looking_for=0.487,
            expected_path=[False, False, False, False, True, True]
        )

        self.assert_can_find_coefficient(
            start=1.5, looking_for=1.487,
            expected_path=[False, True, True]
        )
        self.assert_can_find_coefficient(
            start=1.45, looking_for=1.487,
            expected_path=[True, False, True]
        )
        self.assert_can_find_coefficient(
            start=1.25, looking_for=1.487,
            expected_path=[True, True, True, True, True, False, True]
        )
