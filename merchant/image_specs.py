from django.core.files.base import ContentFile

from imagekit import ImageSpec
from pilkit.processors import ResizeToFit


class Thumbnail(ImageSpec):
    processors = [ResizeToFit(height=100)]
    format = 'PNG'
    options = {'quality': 90}


class ThumbnailGenerator(object):
    spec = Thumbnail
    _instance = None

    def __init__(self, fields):
        self.fields = fields

    def __get__(self, instance, owner):
        self._instance = instance
        return self

    def generate_for(self, *fields):
        for f in fields:
            self.generate_thumbnail(self._instance, f, self.fields[f])

    def generate_thumbnail(self, obj, field_name, thumb_name):
        im_field = getattr(obj, field_name)
        with im_field.open() as image:
            with ContentFile(image.read()) as f:
                im_field.save(im_field.name, f, save=False)
                f.seek(0)
                image_generator = self.spec(source=f)
                thumb = image_generator.generate()
                thumb.seek(0)
                getattr(obj, thumb_name).save(im_field.name, thumb, save=False)
