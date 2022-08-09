from django.contrib import admin

from merchant_extension.models import JobChecklist

from ..forms import JobAnswerForm
from .base import AnswerNestedInline, BaseSectionInline, ChecklistAdmin, ChecklistQuestionNestedInline


class JobAnswerNestedInline(AnswerNestedInline):
    form = JobAnswerForm


class JobChecklistQuestionNestedInline(ChecklistQuestionNestedInline):
    inlines = [JobAnswerNestedInline, ]


class JobChecklistSectionInline(BaseSectionInline):
    inlines = [JobChecklistQuestionNestedInline, ]


@admin.register(JobChecklist)
class JobChecklistAdmin(ChecklistAdmin):
    inlines = [JobChecklistSectionInline]
    exclude = ('invite_text', 'thanks_text', 'checklist_type')
