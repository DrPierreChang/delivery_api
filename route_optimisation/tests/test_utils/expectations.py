from typing import List

from django.test import TestCase


class ExpectationCheck:
    def check(self, test_case: TestCase, *args, **kwargs):
        raise NotImplementedError()


class BaseExpectation:
    def __init__(self):
        self.checklist: List[ExpectationCheck] = []

    def check(self, test_case: TestCase, **kwargs):
        for check in self.checklist:
            check.check(test_case, **kwargs)

    def add_check(self, check: ExpectationCheck):
        self.checklist.append(check)
