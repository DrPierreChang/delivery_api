from __future__ import unicode_literals

from django.db import models

from base.utils import get_custom_upload_path


class SampleFile(models.Model):
    CSV_IMPORT = 'csv_import'
    CSV_SCHEDULE_AND_CAPACITY_IMPORT = 'schedule_and_capacity_csv_import'

    _categories = (
        (CSV_IMPORT, 'CSV Import Example'),
        (CSV_SCHEDULE_AND_CAPACITY_IMPORT, 'Schedule and Capacity CSV Import Example'),
    )

    file = models.FileField(upload_to=get_custom_upload_path)
    name = models.CharField(max_length=256, blank=True)
    category = models.CharField(max_length=256, choices=_categories, unique=True)
    comment = models.TextField(blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    changed_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        super(SampleFile, self).save(*args, **kwargs)

    @property
    def name_of_file(self):
        return self.name or self.file.name

    def __str__(self):
        return '[{}]: {}'.format(self.category, self.name_of_file)
