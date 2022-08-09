from __future__ import absolute_import, unicode_literals

from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_202_ACCEPTED

from base.utils.views import ReadOnlyDBActionsViewSetMixin
from custom_auth.permissions import UserIsAuthenticated
from radaro_utils.permissions import IsAdminOrManager
from tasks.celery_tasks.csv import CSVParserTask, confirm_bulk_upload_v2, generate_orders_from_csv_v2
from tasks.models.bulk import BulkDelayedUpload, CSVOrdersFile
from tasks.permissions import CanProcessBulkUpload

from .serializers.core import BulkDelayedUploadSerializer
from .serializers.csv import CSVOrderPrototypeChunkSerializer, OrderPrototypeErrorSerializer


class UploadDelayedTaskViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                               mixins.ListModelMixin, viewsets.GenericViewSet):
    parser_classes = (MultiPartParser, FormParser,)
    permission_classes = [UserIsAuthenticated, IsAdminOrManager]
    method = BulkDelayedUpload.NO_INFO
    queryset = BulkDelayedUpload.objects.all()
    file_queryset = CSVOrdersFile.objects.all()

    def get_queryset(self):
        return self.queryset.filter(merchant=self.request.user.current_merchant)

    def _create_bulk_upload(self):
        task = self.queryset.create(creator=self.request.user,
                                    merchant=self.request.user.current_merchant,
                                    method=self.method,
                                    uploaded_from=self.request.headers.get('user-agent', ''))
        return task

    def _create_csv_file(self, bulk, file_):
        csv_file = self.file_queryset.create(bulk=bulk, file=file_)
        return csv_file

    def create_task(self):
        file_ = self.request.data.get('file', None)
        if not file_:
            raise NotFound('Field "file" was not found.')

        bulk = self._create_bulk_upload()
        csv_file = self._create_csv_file(bulk=bulk, file_=file_)
        return bulk, csv_file


class CsvBulkView(ReadOnlyDBActionsViewSetMixin, UploadDelayedTaskViewSet):
    queryset = BulkDelayedUpload.objects.filter(csv_file__isnull=False).select_related('csv_file')
    serializer_class = BulkDelayedUploadSerializer
    method = BulkDelayedUpload.WEB
    chunk_serializer_class = CSVOrderPrototypeChunkSerializer
    error_prototype_serializer = OrderPrototypeErrorSerializer

    def create(self, request, *args, **kwargs):
        bulk, csv_file = self.create_task()
        if bulk.status != BulkDelayedUpload.FAILED:
            task = CSVParserTask(bulk, request.auth)
        if bulk.is_in(BulkDelayedUpload.CREATED):
            bulk = task.generate_preview()

        if task.parser:
            task.parser.finish()

        resp = {'task': self.get_serializer(instance=bulk).data}
        if bulk.status == BulkDelayedUpload.READY:
            resp['orders'] = [order.content for order in bulk.prototypes.all().only('content')]
        else:
            resp['errors'] = self.error_prototype_serializer(bulk.errors.only('errors', 'line'), many=True).data
        return Response(data=resp, status=HTTP_200_OK)

    @action(methods=['post'], detail=True, permission_classes=[UserIsAuthenticated, IsAdminOrManager, CanProcessBulkUpload])
    def confirm(self, request, *args, **kwargs):
        task = self.get_object()
        if task.status == BulkDelayedUpload.COMPLETED and task.prototypes.count():
            task.event('Saving data.', BulkDelayedUpload.INFO, BulkDelayedUpload.IN_PROGRESS)
            task.save()
            confirm_bulk_upload_v2.delay(task.id)
            return Response(data=BulkDelayedUploadSerializer(task).data, status=HTTP_202_ACCEPTED)
        elif not task.is_in(BulkDelayedUpload.COMPLETED):
            raise APIException('Task is not completed.')
        else:
            raise APIException('Nothing to save.')

    @action(methods=['post'], detail=True, permission_classes=[UserIsAuthenticated, IsAdminOrManager, CanProcessBulkUpload])
    def process(self, request, *args, **kwargs):
        task = self.get_object()
        if task.status == BulkDelayedUpload.READY:
            generate_orders_from_csv_v2.delay(task.id, request.auth)
        else:
            raise APIException('Task is not ready for processing.')
        return Response(data=self.get_serializer(task).data, status=HTTP_202_ACCEPTED)
