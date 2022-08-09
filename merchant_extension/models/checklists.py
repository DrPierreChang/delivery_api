from django.db import models

from .base import Checklist


class JobChecklistManager(models.Manager):
    def get_queryset(self):
        return super(JobChecklistManager, self).get_queryset().filter(checklist_type=Checklist.JOB)


class JobChecklist(Checklist):
    objects = JobChecklistManager()

    class Meta:
        proxy = True


class StartOfDayChecklistManager(models.Manager):
    def get_queryset(self):
        return super(StartOfDayChecklistManager, self).get_queryset().filter(checklist_type=Checklist.START_OF_DAY)

    def create(self, **kwargs):
        return super(StartOfDayChecklistManager, self).create(**kwargs, checklist_type=Checklist.START_OF_DAY)


class StartOfDayChecklist(Checklist):
    objects = StartOfDayChecklistManager()

    class Meta:
        proxy = True

    def save(self, *args, **kwargs):
        if not self.id:
            self.checklist_type = self.START_OF_DAY
        super(StartOfDayChecklist, self).save(*args, **kwargs)


class EndOfDayChecklistManager(models.Manager):
    def get_queryset(self):
        return super(EndOfDayChecklistManager, self).get_queryset().filter(checklist_type=Checklist.END_OF_DAY)

    def create(self, **kwargs):
        return super(EndOfDayChecklistManager, self).create(**kwargs, checklist_type=Checklist.END_OF_DAY)


class EndOfDayChecklist(Checklist):
    objects = EndOfDayChecklistManager()

    class Meta:
        proxy = True

    def save(self, *args, **kwargs):
        if not self.id:
            self.checklist_type = self.END_OF_DAY
        super(EndOfDayChecklist, self).save(*args, **kwargs)


class SurveyManager(models.Manager):
    def get_queryset(self):
        return super(SurveyManager, self).get_queryset().filter(checklist_type=Checklist.SURVEY)

    def get_surveys_merchant(self, merchant):
        return Survey.objects.filter(pk=merchant.customer_survey_id)

    def get_surveys_subbranding(self, merchant):
        return Survey.objects.filter(sub_brands__merchant=merchant) \
            if merchant.use_subbranding else Survey.objects.none()

    def get_surveys_orders(self, merchant):
        from tasks.models import Order

        from .checklist_results import SurveyResult
        orders = Order.objects.filter(merchant=merchant)
        surveys_id = SurveyResult.objects.filter(
            pk__in=orders.values_list('customer_survey', flat=True)
        ).values_list('checklist', flat=True)
        return Survey.objects.filter(pk__in=surveys_id)

    def related_for_merchant(self, merchant):
        surveys_merchant = self.get_surveys_merchant(merchant)
        surveys_subbranding = self.get_surveys_subbranding(merchant)
        surveys_orders = self.get_surveys_orders(merchant)
        return (surveys_merchant | surveys_subbranding | surveys_orders).distinct('id')


class Survey(Checklist):
    objects = SurveyManager()

    class Meta:
        proxy = True

    def save(self, *args, **kwargs):
        if not self.id:
            self.checklist_type = self.SURVEY
        super(Survey, self).save(*args, **kwargs)
