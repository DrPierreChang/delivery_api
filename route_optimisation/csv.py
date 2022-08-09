from django.conf import settings
from django.utils.functional import cached_property

import pandas as pd

from merchant.models import Merchant
from radaro_utils.radaro_csv import mappers
from radaro_utils.radaro_csv.backends import PandasWritingCSVBackend
from radaro_utils.radaro_csv.mappers.pandas import FormatDateDataFrameFilter
from radaro_utils.radaro_csv.parsing.base import QuerySetChunkMappingWriter
from radaro_utils.radaro_csv.rest_framework.mappers import QuerySetChunkMapper
from route_optimisation.api.web.serializers.csv import CSVRouteOptimisationSerializer
from route_optimisation.models import RoutePoint
from route_optimisation.models.route_point import RoutePointQuerySet


class RoutePointsToDataFrameFilter(mappers.BaseFilter):
    @property
    def add_order_columns(self):
        return self._add_order_columns

    @property
    def add_hub_columns(self):
        return self._add_hub_columns

    @property
    def add_columns_with_dates(self):
        return 'deliver_after', 'deliver_before', 'pickup_after', 'pickup_before'

    @property
    def add_columns_with_times(self):
        return 'predicted_arrival_time', 'predicted_departure_time'

    def __init__(self, mapper):
        super().__init__(mapper)
        self._add_order_columns = set(RoutePointQuerySet.order_fields().values())
        self._add_order_columns.discard(RoutePointQuerySet.HIDDEN)
        self._add_hub_columns = set(RoutePointQuerySet.hub_fields().values())
        self._add_hub_columns.discard(RoutePointQuerySet.HIDDEN)

    def filter(self, value):
        add_order_values = value.order_fields_for_csv()
        order_df = pd.DataFrame.from_dict(add_order_values, orient='index', columns=self.add_order_columns)
        order_df = order_df.astype({'order_id': 'str'})  # it is necessary that the field is not converted to float

        add_hub_values = value.hub_fields_for_csv()
        hub_df = pd.DataFrame.from_dict(add_hub_values, orient='index', columns=self.add_hub_columns)
        hub_df = hub_df.astype({'hub_id': 'str'})

        original_df = self._mapper.mapper(value)
        return original_df.join(order_df.append(hub_df, verify_integrity=True, sort=True))


class RouteOptimisationCSVWriteMapper(QuerySetChunkMapper):
    """
    All instances of parsers share the same mapper and backend, so it's important not to store any
    cached context or another data.
    """
    serializer = CSVRouteOptimisationSerializer()

    class ContextWriteMapper(mappers.FlowMapper):
        filter_flow = (RoutePointsToDataFrameFilter, FormatDateDataFrameFilter)

        def __init__(self, context, mapper):
            self.mapper = mapper
            self.context = context
            self.index_col = mapper.index_col
            super(RouteOptimisationCSVWriteMapper.ContextWriteMapper, self).__init__()

        @property
        def date_fields(self):
            source = self.basic_flow[0]
            return {
                'columns': source.add_columns_with_dates + source.add_columns_with_times,
                'formats': {
                    **{k: self.context['date_format'] for k in source.add_columns_with_dates},
                    **{k: self.context['time_format'] for k in source.add_columns_with_times}
                }
            }

        @property
        def timezone(self):
            return self.context['timezone']

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def using_context(self, context):
        return self.ContextWriteMapper(context, self)


class RouteOptimisationQSWriter(QuerySetChunkMappingWriter):
    queryset = RoutePoint.objects
    mapper_class = RouteOptimisationCSVWriteMapper
    backend = PandasWritingCSVBackend()

    _date_formats = {
        Merchant.LITTLE_ENDIAN: {'python': '%d/%m/%Y %X', 'psql': 'DD/MM/YYYY HH24:MI:SS'},
        Merchant.MIDDLE_ENDIAN: {'python': '%m/%d/%Y %X', 'psql': 'MM/DD/YYYY HH24:MI:SS'},
        Merchant.BIG_ENDIAN: {'python': '%Y-%m-%d %X', 'psql': 'YYYY-MM-DD HH24:MI:SS'}
    }

    @cached_property
    def timezone(self):
        return str(self.merchant.timezone) if self.merchant else settings.TIME_ZONE

    def get_queryset(self):
        qs = self.queryset.filter(route__optimisation=self.filter_params['optimisation'])
        qs = qs.order_by('route_id', 'number')
        return self.mapper.update_qs(qs)

    @cached_property
    def date_format(self):
        return self.merchant.date_format if self.merchant else settings.DEFAULT_DATE_FORMAT

    @property
    def mapper_context(self):
        return {
            'date_format': self._date_formats[self.date_format]['python'],
            'time_format': '%H:%M',
            'timezone': self.timezone,
        }

    @property
    def merchant(self):
        return self.model_obj.merchant

    @property
    def initiator(self):
        return self.model_obj.initiator

    def __init__(self, model_obj, params, **kwargs):
        self.chunksize = settings.BULK_JOB_REPORT_BATCH_SIZE
        self.filter_params = params
        super().__init__(model_obj, **kwargs)
