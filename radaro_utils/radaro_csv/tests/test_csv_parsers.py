from __future__ import absolute_import, unicode_literals

import re
from collections import OrderedDict

from django.test import tag, testcases

from rest_framework import fields, serializers

from ..backends import PandasWritingCSVBackend
from .utils import Customer, FakeCSVModel, FakeWriteCSVModel, Order


def remap(f):
    return re.sub(r'\*', '', re.sub(r' ', '_', f.lower()))


test_headers = ["Customer name*", "Job address*", "Driver ID", "Job deadline", "Comment", "Customer_Email",
                "Customer Phone", "Job name"]
test_map_headers = OrderedDict((f, remap(f)) for f in test_headers)
reversed_test_map_headers = OrderedDict(map(reversed, test_map_headers.items()))


class TestOrderSerializer(serializers.Serializer):
    job_address = fields.CharField(allow_blank=False, required=True, source='deliver_address', max_length=2048)

    job_name = fields.CharField(source='title', max_length=2048, required=False)
    comment = fields.CharField(required=False, max_length=2048)
    customer_name = fields.CharField(required=True, max_length=2048, source='customer.name')
    customer_phone = fields.CharField(required=False, max_length=2048, source='customer.phone')
    customer_email = fields.CharField(required=False, max_length=2048, source='customer.email')
    driver_id = fields.IntegerField(required=False, allow_null=True)
    job_deadline = fields.CharField(source='deliver_before', required=False)

    def to_representation(self, instance):
        dt = super(TestOrderSerializer, self).to_representation(instance)
        return {reversed_test_map_headers[k]: v for k, v in dt.items()}


test_customers = [
    Customer(name="John Doe", phone="442079460858", email="example@example.com"),
    Customer(name="Judy Doe", phone="442079460980", email="example@not.example.com"),
    Customer(name="Peter Doe", phone=None, email=None)
]
test_data = [Order(customer=c, **data) for c, data in zip(test_customers, [
    {'deliver_address': "5 Ufford Street, London, United Kingdom",
     'driver_id': None,
     'deliver_before': "03.03.18 03:00",
     'comment': "Test task in csv",
     'title': "John\'s job"},
    {'deliver_address': "77 Millais Road, London",
     'driver_id': 3636491,
     'deliver_before': "12.12.19 5:00+0",
     'comment': "Some description",
     'title': None},
    {'deliver_address': "51.569064, -0.094444",
     'driver_id': None,
     'deliver_before': "07.03.18 03:00",
     'comment': None,
     'title': None}
])]

result_dict = dict((
    (u'deliver_address', u'5 Ufford Street, London, United Kingdom'),
    (u'title', u'John\'s job'),
    (u'customer', {u'phone': u'442079460858', u'name': u'John Doe', u'email': u'example@example.com'}),
    (u'deliver_before', u'03.03.18 03:00'),
    (u'comment', u'Test task in csv')
))


@tag('need_repair')
class CSVProcessingTest(testcases.TestCase):
    REPEATS = 3

    @classmethod
    def setUpClass(cls):
        super(CSVProcessingTest, cls).setUpClass()
        cls.fake_qs = test_data * cls.REPEATS

    def setUp(self):
        self.file_model = FakeWriteCSVModel()
        writer = CSVOrderWriter(self.file_model, data_to_write=self.fake_qs)
        for _ in writer.write():
            continue
        writer.finish()

    def test_1_csv_data_writer(self):
        _f = self.file_model.open_file(mode='rt')
        self.assertEqual(len(test_data) * self.REPEATS + 1, len(tuple(_f)))
        self.file_model.close_file(_f)

    def test_2_csv_model_parser(self):
        csv = FakeCSVModel()
        csv.detect_metadata()
        parser = CSVOrderParser(csv)
        objs = list(parser)
        ser = TestOrderSerializer(data=objs[0])
        ser.is_valid(raise_exception=True)
        self.assertDictEqual(dict(ser.validated_data), result_dict)
