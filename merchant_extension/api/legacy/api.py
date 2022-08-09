from django.db.models import Prefetch, Q

from rest_framework import mixins, views, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from rest_condition import C

from base.permissions import IsDriverOrReadOnly, IsObserver
from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from merchant_extension.admin.views import SurveyResultsDownloadCSVMixin
from merchant_extension.models import Checklist, Question, ResultChecklist, ResultChecklistAnswer, Survey, SurveyResult
from merchant_extension.permissions import EoDChecklistEnabled, SoDChecklistEnabled
from radaro_utils.permissions import IsAdminOrManager
from reporting.decorators import log_fields_on_object
from tasks.api.legacy.serializers import DriverOrderSerializer
from tasks.mixins.order_status import OrderStatus
from tasks.models import Order

from .serializers import DailyChecklistRequestSerializer, ResultChecklistSerializer
from .serializers.survey import (
    SurveyCSVDownloadRequestSerializer,
    SurveyLightSerializer,
    SurveyResultRetrieveSerializer,
    SurveyRetrieveSerializer,
)


class ResultChecklistViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    # don't use read db here because of table lock
    queryset = ResultChecklist.objects.select_related('checklist')
    serializer_class = ResultChecklistSerializer
    permission_classes = [UserIsAuthenticated, IsDriverOrReadOnly]

    def get_queryset(self):
        qs = super(ResultChecklistViewSet, self).get_queryset()
        if self.request.method == 'GET':
            prf_answers = Prefetch(
                'result_answers',
                queryset=ResultChecklistAnswer.objects.all().select_related('answer__question')
                    .order_by('answer__question__consecutive_number')
                    .prefetch_related('photos')
            )

            prf_questions = Prefetch(
                'checklist__sections__questions',
                queryset=Question.objects.all().order_by('consecutive_number')
            )
            return qs.prefetch_related('confirmation_photos', prf_answers, prf_questions)
        return qs

    def filter_queryset(self, queryset):
        queryset = super(ResultChecklistViewSet, self).filter_queryset(queryset)
        merchant = self.request.user.current_merchant
        orders_qs = Order.objects.filter(merchant=merchant).exclude(driver_checklist__isnull=True)
        daily_filter = Q(driver__merchant=merchant,
                         checklist__checklist_type__in=[Checklist.START_OF_DAY, Checklist.END_OF_DAY])
        if self.request.user.is_driver:
            orders_filter = Q(driver=self.request.user)
            if self.request.method == 'GET':
                orders_filter |= Q(status=OrderStatus.NOT_ASSIGNED)
            orders_qs = orders_qs.filter(orders_filter)
            daily_filter &= Q(driver=self.request.user)
        job_checklist_filter = Q(id__in=orders_qs.values_list('driver_checklist_id', flat=True),
                                 checklist__checklist_type=Checklist.JOB)
        return queryset.filter(job_checklist_filter | daily_filter)

    @action(methods=['get'], detail=False, permission_classes=[UserIsAuthenticated, SoDChecklistEnabled],
            url_path='start-of-day')
    def start_of_day(self, request, **kwargs):
        if request.user.is_driver:
            driver = request.user
        else:
            request_serializer = DailyChecklistRequestSerializer(
                data=request.query_params,
                context={'request': request},
            )
            request_serializer.is_valid(raise_exception=True)
            driver = request_serializer.validated_data['driver']
        instance = self.get_queryset().get_current_sod_checklist(driver)
        serializer = self.get_serializer(instance)
        return Response(data=serializer.data)

    @action(methods=['get'], detail=False, permission_classes=[UserIsAuthenticated, EoDChecklistEnabled],
            url_path='end-of-day')
    def end_of_day(self, request, **kwargs):
        if request.user.is_driver:
            driver = request.user
        else:
            request_serializer = DailyChecklistRequestSerializer(
                data=request.query_params,
                context={'request': request},
            )
            request_serializer.is_valid(raise_exception=True)
            driver = request_serializer.validated_data['driver']
        instance = self.get_queryset().get_current_eod_checklist(driver)
        serializer = self.get_serializer(instance)
        return Response(data=serializer.data)

    @action(methods=['post'], detail=True)
    @log_fields_on_object(fields=['is_correct', ])
    def answers(self, request, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data={'answers': request.data.get('answers')})
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(data=serializer.data)

    @action(methods=['put', 'patch'], detail=True)
    def confirmation(self, request, **kwargs):
        instance = self.get_object()
        expected_fields = ['confirmation_photos', 'confirmation_signature', 'confirmation_comment']
        data = {"pre_{}".format(k): request.data[k] for k in expected_fields if k in request.data}
        driver_order_serializer = DriverOrderSerializer(instance.order, data=data,
                                                        partial=True, context={'request': request})
        driver_order_serializer.is_valid(raise_exception=True)
        driver_order_serializer.save()

        return Response(data=self.get_serializer(instance).data)


class SurveyResultViewSet(ReadOnlyDBActionsViewSetMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):

    queryset = SurveyResult.objects.all()
    serializer_class = SurveyResultRetrieveSerializer
    permission_classes = [UserIsAuthenticated, C(IsAdminOrManager) | C(IsObserver)]

    def get_queryset(self):
        qs = super(SurveyResultViewSet, self).get_queryset()
        sub_brands_customer_surveys = self.request.user.current_merchant.subbrandings.\
            values_list('customer_survey_id', flat=True)
        merchant_customer_survey_id = self.request.user.current_merchant.customer_survey_id
        result_answers_prefetch = Prefetch(
            'result_answers',
            queryset=ResultChecklistAnswer.objects.all().select_related('answer')
        )
        return qs.filter(
            Q(checklist_id=merchant_customer_survey_id) |
            Q(checklist_id__in=sub_brands_customer_surveys)
        ).prefetch_related(result_answers_prefetch)


class SurveyMerchantViewSet(ReadOnlyDBActionsViewSetMixin,
                            mixins.RetrieveModelMixin,
                            viewsets.GenericViewSet):
    queryset = Survey.objects
    serializer_class = SurveyRetrieveSerializer
    permission_classes = (UserIsAuthenticated, C(IsAdminOrManager) | C(IsObserver))

    def filter_queryset(self, queryset):
        merchant = self.request.user.current_merchant
        return super(SurveyMerchantViewSet, self).filter_queryset(queryset).related_for_merchant(merchant)

    @action(methods=['get'], detail=False, url_path='related-surveys')
    def related_surveys(self, request, **kwargs):
        surveys = self.filter_queryset(self.get_queryset())
        serializer = SurveyLightSerializer(surveys, many=True)
        return Response(data=serializer.data)

    @action(methods=['get'], detail=False, url_path='count-surveys-result')
    def count_surveys_result(self, request, **kwargs):
        request_serializer = SurveyCSVDownloadRequestSerializer(data=request.query_params)
        request_serializer.is_valid(raise_exception=True)
        queryset = Order.objects.for_csv(merchant=request.user.current_merchant, **request_serializer.validated_data)
        data = {'count': queryset.count()}
        return Response(data=data)


class SurveyResultCSVView(SurveyResultsDownloadCSVMixin, views.APIView):
    permission_classes = [UserIsAuthenticated, C(IsAdminOrManager) | C(IsObserver)]

    def post(self, request, *args, **kwargs):
        request_serializer = SurveyCSVDownloadRequestSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        params = dict({'merchant': request.user.current_merchant}, **request_serializer.validated_data)
        return self.generate_response(params)
