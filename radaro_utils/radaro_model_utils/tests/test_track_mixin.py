import os

from django.core.files.base import File
from django.db.models.base import ModelBase
from django.template.loader import get_template, render_to_string

import mock
from model_utils import FieldTracker

from .mixins import TestAbstractModelMixin
from .models import TestTrackMixinModel

base_dir = os.path.dirname(__file__)


class TrackMixinTestCase(TestAbstractModelMixin):
    test_model = TestTrackMixinModel

    @classmethod
    def create_model(cls):
        cls.model = ModelBase(
            '__TestModel__' + cls.test_model.__name__, (cls.test_model,),
            {'__module__': cls.test_model.__module__, 'tracker': FieldTracker()}
        )

    def setUp(self):
        self.object = self.model()
        self.object.save()

    def test_image_change(self):
        f_name = 'med_1446103181_image.jpg'
        with open(os.path.join(base_dir, f_name), 'rb') as pic:
            c = File(pic, name=f_name)
            self.object.image = c
            self.object.save()
            sz = self.object.image.size
            sm_sz = self.object.small_image.size
            self.assertEqual((sz, sm_sz), (33645, 1818))

    def test_template_rendering(self):
        self.object.name = 'Test Name'
        self.object.save()
        template = 'This is test template and model name is {}.'
        full_template_name = 'test_template.txt'
        with open(os.path.join(base_dir, '../templates/' + full_template_name), 'wt') as tmpl:
            tmpl.write(template.format('{{ testmodeltesttrackmixinmodel.name }}'))
        plaintext = get_template(full_template_name)
        context = {type(self.object).__name__.lower().replace('__', ''): self.object}
        text = plaintext.render(context)
        text_2 = render_to_string(full_template_name, context)
        self.assertEqual(template.format(self.object.name), text)
        self.assertEqual(text, text_2)

    def test_on_change_hooks(self):
        self.object.name = 'new name'
        self.object.save()
        with mock.patch.object(self.object, '_name_changed_call', return_value=None) as on_name_change:
            with mock.patch.object(self.object, '_on_image_change', return_value=None) as on_image_change:
                self.object.name = 'new name 2'
                self.object.save()
                on_name_change.assert_called_once()
                on_image_change.assert_not_called()
