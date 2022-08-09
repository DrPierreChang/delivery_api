from django.db.models import Prefetch, Q

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from base.permissions import IsDriver
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from merchant_extension.models import Checklist, Question, ResultChecklist, ResultChecklistAnswer
from merchant_extension.permissions import EoDChecklistEnabled, SoDChecklistEnabled
from reporting.decorators import log_fields_on_object
from tasks.models import Order

from .serializers import ResultAnswerSerializer, ResultChecklistSerializer


class DriverChecklistViewSet(ReadOnlyDBActionsViewSetMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [UserIsAuthenticated, IsDriver]
    serializer_class = ResultChecklistSerializer
    answer_serializer_class = ResultAnswerSerializer
    queryset = ResultChecklist.objects.select_related('checklist')

    def get_queryset(self):
        queryset = super().get_queryset()

        user = self.request.user
        job_checklist_ids = (
            Order.aggregated_objects
                .filter(driver_id=user.id, merchant_id=user.current_merchant_id)
                .exclude(driver_checklist__isnull=True)
                .values_list('driver_checklist_id', flat=True)
        )
        queryset = queryset.filter(
            Q(id__in=job_checklist_ids)
            | Q(driver_id=user.id, checklist__checklist_type__in=[Checklist.START_OF_DAY, Checklist.END_OF_DAY])
        )

        if self.request.method == 'GET':
            questions_prefetch = Prefetch(
                'checklist__sections__questions', queryset=Question.objects.all().order_by('consecutive_number'),
            )
            answers_prefetch = Prefetch(
                'result_answers',
                queryset=ResultChecklistAnswer.objects.all().select_related('answer__question')
                    .order_by('answer__question__consecutive_number')
                    .prefetch_related('photos'),
            )
            return queryset.prefetch_related(questions_prefetch, answers_prefetch)
        return queryset

    @action(detail=False, url_path='start-of-day',
            permission_classes=[UserIsAuthenticated, IsDriver, SoDChecklistEnabled])
    def start_of_day(self, request, *args, **kwargs):
        sod_checklist = self.get_queryset().get_current_sod_checklist(request.user)
        return Response(self.get_serializer(sod_checklist).data)

    @action(detail=False, url_path='end-of-day',
            permission_classes=[UserIsAuthenticated, IsDriver, EoDChecklistEnabled])
    def end_of_day(self, request, *args, **kwargs):
        eod_checklist = self.get_queryset().get_current_eod_checklist(request.user)
        return Response(self.get_serializer(eod_checklist).data)

    @action(detail=True, methods=['post'])
    def answer(self, request, *args, **kwargs):
        instance = self.get_object()
        answer_serializer = self.answer_serializer_class(data=request.data, context={'result_checklist': instance})
        answer_serializer.is_valid(raise_exception=True)
        answer_serializer.save()
        return Response(status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['put'])
    @log_fields_on_object()
    def confirm(self, request, *args, **kwargs):
        # Hook used to initiate result checklist postprocessing
        # Hooks: check_sod_checklist_passed, check_eod_checklist_passed, check_job_checklist_passed
        instance = self.get_object()
        instance.save()
        return Response(self.get_serializer(instance).data)
