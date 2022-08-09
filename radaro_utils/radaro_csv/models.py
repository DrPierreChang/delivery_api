from __future__ import absolute_import, unicode_literals

from django.db import models

from jsonfield import JSONField

from radaro_utils.files.utils import delayed_task_upload
from radaro_utils.radaro_csv import meta


class CSVFile(meta.CSVMetadataMixin, models.Model):
    file = models.FileField(upload_to=delayed_task_upload, null=True)
    lines = models.PositiveIntegerField(default=0)
    encoding = models.CharField(max_length=256, blank=True)
    columns = JSONField(default=[])
    original_file_name = models.CharField(max_length=2048, blank=True)
    blank_lines = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True

    def open_file(self, mode='rb'):
        self.file.open(mode)
        return self.file

    def _on_create(self):
        self.detect_metadata()

    def save(self, *args, **kwargs):
        if not self.id:
            self._on_create()
        super(CSVFile, self).save(*args, **kwargs)
