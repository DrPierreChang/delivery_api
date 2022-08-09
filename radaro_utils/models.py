from django.core.files.base import ContentFile
from django.db import models

from PIL import Image

from base.utils import get_upload_path_100x100
from radaro_utils.files.utils import get_upload_path


class ResizeImageMixin(object):

    def rotate_image_by_exif(self, image):
        if hasattr(image, '_getexif') and image._getexif():
            from PIL import ExifTags
            exif = dict((ExifTags.TAGS[k], v) for k, v in image._getexif().items() if k in ExifTags.TAGS)
            orientation = exif.get('Orientation')
            if orientation is 6:
                image = image.rotate(-90)
            elif orientation is 8:
                image = image.rotate(90)
            elif orientation is 3:
                image = image.rotate(180)
            elif orientation is 2:
                image = image.transpose(Image.FLIP_LEFT_RIGHT)
            elif orientation is 5:
                image = image.rotate(-90).transpose(Image.FLIP_LEFT_RIGHT)
            elif orientation is 7:
                image = image.rotate(90).transpose(Image.FLIP_LEFT_RIGHT)
            elif orientation is 4:
                image = image.rotate(180).transpose(Image.FLIP_LEFT_RIGHT)
        return image

    def resize_image(self, image_field, size=None, save_field=None):
        if not save_field:
            image = Image.open(image_field.file.file)
            im_field = image_field
            name = image_field.name
        else:
            file = ContentFile(image_field.file.file.read())
            image = Image.open(file)
            name_arr = image_field.file.file.name.split('.')

        if not size:
            ratio = image.size[0] / image.size[1]
            size = (int(500 * ratio), 500)

        if save_field:
            name_arr[0] += '_{}x{}'.format(*size)
            name = '.'.join(name_arr)
            im_field = getattr(self, save_field)

        from io import BytesIO
        image_bytes = BytesIO()
        try:
            rotated_image = self.rotate_image_by_exif(image)
            rotated_image = rotated_image.resize(size, Image.ANTIALIAS)
            rotated_image.save(image_bytes, format=image.format)
            im_field.save(name, ContentFile(image_bytes.getvalue()), save=False)
        finally:
            image_bytes.close()


class AttachedPhotoBase(ResizeImageMixin, models.Model):
    image = models.ImageField(upload_to=get_upload_path)
    thumb_image_100x100_field = models.ImageField(null=True, blank=True, editable=False,
                                                  upload_to=get_upload_path_100x100)
    _check_high_resolution = False

    class Meta:
        abstract = True

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        if self.image and not (self._check_high_resolution and self._merchant.high_resolution):
            if self.image.height > 500 or self.image.width > 500:
                self.resize_image(self.image)

        super().save(
            force_insert=force_insert,
            force_update=force_update,
            using=using,
            update_fields=update_fields,
        )

    @property
    def _merchant(self):
        return None

    @property
    def thumb_image_100x100(self):
        if self.thumb_image_100x100_field:
            return self.thumb_image_100x100_field
        else:
            return self.image

    def _on_image_change(self, previous):
        if self.image:
            self.thumbnailer.generate_for('image')
