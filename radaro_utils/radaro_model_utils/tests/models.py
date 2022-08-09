from __future__ import absolute_import, unicode_literals

import uuid

from django.core.files.base import ContentFile, File
from django.db import models

from PIL import Image

from radaro_utils.radaro_model_utils.mixins import TrackMixin


class TestTrackMixinModel(TrackMixin):
    track_fields = {'image', 'name'}

    image = models.ImageField(upload_to=lambda x, y: 'radaro_utils/{}'.format(uuid.uuid4()), null=True)
    name = models.CharField(max_length=128, default='radaro_utils_{}'.format(uuid.uuid4()), null=True)
    small_image = models.ImageField(upload_to=lambda x, y: 'radaro_utils/{}_small'.format(uuid.uuid4()), null=True)

    def _on_image_change(self, previous):
        if self.image:
            with ContentFile(self.image.read()) as f:
                im = Image.open(f)
                im.thumbnail((100, 100), Image.ANTIALIAS)
                with ContentFile(b'') as cf:
                    im.save(cf, "JPEG")
                    self.small_image.save(self.image.name, cf, save=False)

    def _on_name_change(self, previous):
        assert previous != self.name
        self._name_changed_call()

    def _name_changed_call(self):
        pass

    class Meta:
        abstract = True
