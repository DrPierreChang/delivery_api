from django.db import models


class AvailabilityTest(models.Model):
    primary_key = models.CharField(max_length=20, primary_key=True)
    last_access = models.DateTimeField(help_text='Datetime of last access to this model from the celery task')
