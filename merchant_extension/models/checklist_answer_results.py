import re
from datetime import datetime

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import models
from django.db.models import F
from django.db.models.signals import post_save

from model_utils import FieldTracker

from merchant.image_specs import ThumbnailGenerator
from radaro_utils.images.exif import prepare_exif_gps
from radaro_utils.models import AttachedPhotoBase
from radaro_utils.radaro_model_utils.mixins import TrackMixin
from routing.models.locations import Location

from .base import Answer, Question


class ResultAnswerQuerySet(models.QuerySet):
    def annotate_correct_answer(self):
        return self.annotate(correct_answer=F('answer__is_correct'))


class ResultChecklistAnswer(models.Model):
    result_checklist = models.ForeignKey(
        'ResultChecklist', related_name='result_answers', on_delete=models.CASCADE
    )
    question = models.ForeignKey(
        Question, related_name='result_answers',
        on_delete=models.CASCADE
    )
    answer = models.ForeignKey(
        Answer, related_name='result_checklist_answers', blank=True,
        null=True, on_delete=models.CASCADE
    )
    text = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now=True)

    objects = ResultAnswerQuerySet.as_manager()

    class Meta:
        unique_together = ('question', 'answer', 'result_checklist')
        verbose_name = 'Answer to checklist question'
        verbose_name_plural = 'Answers to checklists questions'

    def answer_attachments_generator(self):
        photos = list(self.photos.values_list('image', flat=True))

        for photo in photos:
            with default_storage.open(photo, 'rb') as conf_file:
                attachment = ContentFile(conf_file.read())
                attachment.name = photo.split('/')[-1]
                yield attachment

    @property
    def answer_text(self):
        return self.text or self.answer.text

    @property
    def choice(self):
        return self.answer.choice

    @property
    def comment(self):
        return self.text

    def __str__(self):
        return f'ResultChecklistAnswer {self.id} ({self.question.text} {self.answer.text})'


class ImageLocation(Location):
    happened_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ('created_at',)

    @staticmethod
    def get_from_exif(gps_info, lat, lon, happened_at=None):
        if lat is None:
            lat, lon, happened_at = prepare_exif_gps(gps_info)
        if lat is None:
            return None

        location = f'{float(lat):.6f},{float(lon):.6f}'

        location_obj = ImageLocation.objects.filter(location=location, happened_at=happened_at).first()
        if location_obj is None:
            location_obj = ImageLocation.objects.create(location=location, happened_at=happened_at)

        return location_obj


class ResultChecklistAnswerPhotoManager(models.Manager):

    def bulk_create(self, objects, signal=True, **kwargs):
        photos = super().bulk_create(objects, **kwargs)
        if signal:
            for photo in photos:
                post_save.send(ResultChecklistAnswerPhoto, instance=photo, created=True)
        return photos


class ResultChecklistAnswerPhoto(TrackMixin, AttachedPhotoBase):
    thumbnailer = ThumbnailGenerator({'image': 'thumb_image_100x100_field'})
    tracker = FieldTracker()
    track_fields = {'image'}

    image_location = models.ForeignKey(ImageLocation, null=True, on_delete=models.SET_NULL)
    happened_at = models.DateTimeField(null=True)
    answer_object = models.ForeignKey(ResultChecklistAnswer, related_name='photos', on_delete=models.CASCADE)

    objects = ResultChecklistAnswerPhotoManager()

    def prepare_exif_from_ios(self, description):
        # Parsed string example
        # TimeZone +03:00, CreationDate 2022:04:20 12:34:23, Latitude -8.66212219975799, Longitude 115.13733400624128
        # Parsing result example
        # {'creation_time_offset': '+03:00', 'creation_time': '2022:04:20 12:34:23',
        #  'latitude': '-8.66212219975799', 'longitude': '115.13733400624128'}

        r = r'(' \
            r'(TimeZone\s*(?P<creation_time_offset>[-+]?\d{1,2}:\d{1,2}))' \
            r'|(CreationDate\s*(?P<creation_time>\d{2,4}:\d{1,2}:\d{1,2}\s*\d{1,2}:\d{1,2}:\d{1,2}))' \
            r'|(Latitude\s*(?P<latitude>[-.0-9]+))' \
            r'|(Longitude\s*(?P<longitude>[-.0-9]+))' \
            r'|[\s,])*'

        values = re.search(r, description).groupdict()
        values = {key: value for key, value in values.items() if value is not None}
        return values

    def prepare_exif(self, merchant):
        try:
            # This method crashes when processing some png files. That's why you need try/catch.
            exif = self.image.file.image.getexif()
            if not exif:
                return
        except AttributeError:
            return

        tags = {
            0x8825: 'gps_info',
            0x9003: 'creation_time',
            0x9011: 'creation_time_offset',
            0x010e: 'description',
        }
        image_info = {tags[key]: value for key, value in dict(exif).items() if key in tags}

        if 'description' in image_info:
            description = self.prepare_exif_from_ios(image_info['description'])
            image_info = {**image_info, **description}

        if 'gps_info' in image_info or ('latitude' in image_info and 'longitude' in image_info):
            gps_info = image_info.get('gps_info', None)
            latitude = image_info.get('latitude', None)
            longitude = image_info.get('longitude', None)
            self.image_location = ImageLocation.get_from_exif(gps_info, latitude, longitude)

        if 'creation_time' in image_info and 'creation_time_offset' in image_info:
            try:
                happened_at_str = f"{image_info['creation_time']} {image_info['creation_time_offset'].replace(':', '')}"
                self.happened_at = datetime.strptime(happened_at_str, '%Y:%m:%d %H:%M:%S %z')
                return
            except ValueError:
                pass
        if self.image_location and self.image_location.happened_at is not None:
            self.happened_at = self.image_location.happened_at
            return
        if 'creation_time' in image_info:
            try:
                happened_at = datetime.strptime(image_info['creation_time'], '%Y:%m:%d %H:%M:%S')
                self.happened_at = merchant.timezone.localize(happened_at)
                return
            except ValueError:
                pass
