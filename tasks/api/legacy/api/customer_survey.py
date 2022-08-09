from django.db.models import Prefetch

from rest_framework import mixins, status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from base.utils.views import ReadOnlyDBActionsViewSetMixin
from merchant_extension.models import Question, SurveyResult
from tasks.models import Order

from ..serializers.orders import CustomerSurveySerializer
from .customer import CustomerViewSet
from .mixins import ObjectByUIDB64ApiBase


class CustomerSurveysViewSet(ReadOnlyDBActionsViewSetMixin,
                             mixins.RetrieveModelMixin,
                             mixins.CreateModelMixin,
                             ObjectByUIDB64ApiBase):
    queryset = SurveyResult.objects.all()
    serializer_class = CustomerSurveySerializer
    uidb64_lookup_viewset = CustomerViewSet

    def _get_order(self):
        qs = Order.objects.filter(customer_id=self._object_id)
        return get_object_or_404(qs, order_token=self.kwargs.get('customer_order_order_token'))

    def get_queryset(self):
        queryset = super(CustomerSurveysViewSet, self).get_queryset()
        prf_questions = Prefetch(
            'checklist__sections__questions',
            queryset=Question.objects.all().order_by('consecutive_number').prefetch_related('answers')
        )
        return queryset.prefetch_related(prf_questions)

    def create(self, request, *args, **kwargs):
        order = self._get_order()
        survey_template = order.customer_survey_template
        if not survey_template:
            return Response(status=status.HTTP_403_FORBIDDEN)

        if not order.customer_survey_id:
            obj = SurveyResult.objects.create(checklist=survey_template)
            order.customer_survey = obj
            order.save()
        else:
            obj = order.customer_survey

        serializer = self.get_serializer(obj)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(methods=['POST'], detail=True)
    def results(self, request, **kwargs):
        res_survey = self.get_object()
        serializer = self.get_serializer(res_survey, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(status=status.HTTP_201_CREATED)
