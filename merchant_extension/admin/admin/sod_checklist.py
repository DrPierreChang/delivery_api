from django.contrib import admin

from merchant_extension.models import StartOfDayChecklist
from notification.push_messages.utils import send_on_event_data_notifications
from reporting.models import Event
from reporting.signals import send_create_event_signal

from ..forms import StartOfDayAnswerForm
from .base import AnswerNestedInline, BaseSectionInline, ChecklistAdmin, ChecklistQuestionNestedInline


class StartOfDayAnswerNestedInline(AnswerNestedInline):
    form = StartOfDayAnswerForm


class StartOfDayChecklistQuestionNestedInline(ChecklistQuestionNestedInline):
    inlines = [StartOfDayAnswerNestedInline, ]


class StartOfDayChecklistSectionInline(BaseSectionInline):
    inlines = [StartOfDayChecklistQuestionNestedInline, ]


@admin.register(StartOfDayChecklist)
class StartOfDayChecklistAdmin(ChecklistAdmin):
    inlines = [StartOfDayChecklistSectionInline]
    exclude = ('invite_text', 'thanks_text', 'checklist_type')

    def save_model(self, request, obj, form, change):
        if change:
            event = Event.generate_event(
                self,
                initiator=request.user,
                object=obj,
                event=Event.MODEL_CHANGED
            )
            send_create_event_signal(events=[event])
            merchants = obj.merchant_set.all() or obj.sod_merchants.all()
            obj_preview = {'id': obj.id, 'model': type(obj).__name__}
            for merchant in merchants:
                send_on_event_data_notifications(merchant=merchant, obj_preview=obj_preview, event=Event.MODEL_CHANGED)
        super().save_model(request, obj, form, change)
