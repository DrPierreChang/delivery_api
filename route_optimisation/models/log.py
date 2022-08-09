from django.contrib.postgres.fields import JSONField
from django.db import models


class ROLog(models.Model):
    log = JSONField(default=dict, blank=True)
