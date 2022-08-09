from django.contrib import admin
from django.forms import inlineformset_factory

from nested_admin.nested import NestedModelAdmin

from merchant_extension.models import Question, Section, Survey, SurveyResult
from radaro_utils.radaro_admin.admin import Select2FiltersMixin

from ..forms import SurveyAnswerForm
from ..views import CMSSurveyResultsView, get_survey_merchants_view
from .base import (
    AnswerNestedInline,
    BaseQuestionNestedInline,
    BaseSectionInline,
    ResultChecklistAnswerInline,
    filtered_question_category_formset,
    unique_field_formset,
)

admin.site.register_view(r'survey-results/', name='Survey results export',
                         view=CMSSurveyResultsView.as_view(), visible=True)

admin.site.register_view(r'survey-merchants/?$', urlname='cms-survey-merchants',
                         view=get_survey_merchants_view, visible=False)


class SurveyAnswerNestedInline(AnswerNestedInline):
    form = SurveyAnswerForm


class SurveyQuestionNestedInline(BaseQuestionNestedInline):
    inlines = [SurveyAnswerNestedInline, ]

    formset = inlineformset_factory(
        Section, Question,
        formset=filtered_question_category_formset(
            base_class=unique_field_formset(('consecutive_number', 'section_id')),
            question_categories=Question.survey_question_categories
        ),
        fields='__all__'
    )


class SurveySectionInline(BaseSectionInline):
    inlines = [SurveyQuestionNestedInline, ]


@admin.register(Survey)
class SurveyAdmin(NestedModelAdmin):
    inlines = [SurveySectionInline, ]
    list_display = ('title',)
    exclude = ('checklist_type',)


@admin.register(SurveyResult)
class SurveyResultAdmin(Select2FiltersMixin, admin.ModelAdmin):
    inlines = [ResultChecklistAnswerInline, ]
    list_display = ('id', 'checklist', 'customer_order', 'created_at',)
    list_select_related = ('checklist', 'customer_order')
    list_filter = ('checklist__checklist_type',)
    search_fields = ('id', 'customer_order__order_id')
    exclude = ('driver',)
