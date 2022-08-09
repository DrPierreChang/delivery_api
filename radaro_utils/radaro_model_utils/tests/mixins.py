from django import test
from django.db import connection
from django.db.models.base import ModelBase


class TestAbstractModelMixin(test.TestCase):
    test_model = None

    @classmethod
    def create_model(cls):
        cls.model = ModelBase(
            '__TestModel__' + cls.test_model.__name__, (cls.test_model,),
            {'__module__': cls.test_model.__module__}
        )

    @classmethod
    def setUpTestData(cls):
        super(TestAbstractModelMixin, cls).setUpTestData()
        cls.create_model()

        # Create the schema for our test model
        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(cls.model)
