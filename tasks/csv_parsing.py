from django.conf import settings
from django.utils.functional import cached_property

import pandas as pd
from pandas.io.json import json_normalize

from merchant.models import Merchant
from radaro_utils.radaro_csv import mappers
from radaro_utils.radaro_csv.backends import PandasCSVBackend, PandasWritingCSVBackend
from radaro_utils.radaro_csv.backends.unicode_csv import UnicodeCSVReadBackend
from radaro_utils.radaro_csv.mappers.pandas import FormatDateDataFrameFilter
from radaro_utils.radaro_csv.parsing.base import CSVModelMappingReader, QuerySetChunkMappingWriter
from radaro_utils.radaro_csv.rest_framework.field_validators import HeaderControl
from radaro_utils.radaro_csv.rest_framework.mappers import PandasReadMapper, QuerySetChunkMapper, UnicodeCSVReadMapper
from radaro_utils.utils import shortcut_link_safe
from tasks.api.legacy.serializers.csv import (
    CSVOrderReportSerializer,
    CSVOrderSerializer,
    ExtendedCSVOrderReportSerializer,
)
from tasks.models import Order

_messages = {
    'required_fields': 'Some required columns are not found or have invalid names.',
    'optional_skipped': 'Skipped optional columns. They are missing or have invalid names.',
    'required': 'Missing required field. Row skipped.',
    'invalid_format': 'Invalid file format.',
    'critical': 'Sorry, server unable to process file. We are investigating this error.',
    'row_invalid': 'Found invalid rows.',
    'finished': 'File processing has been finished.',
    'preview_finished': 'Preview generating was finished.',
    'preview_errors': 'There were errors during preview generating. Please, correct file.',
    'empty_file': 'File has no rows with correct data.',
    'low_balance': 'CSV upload was disabled, because merchant is blocked due to low balance.',
    'unicode_error': 'File you upload contains unsupported non-unicode symbols. '
                     'Please, check line {} and try to upload again.',
    'continued': 'File processing is continued.',
    'processed_amount': 'Number of lines that have been processed',
    'saved_amount': 'Number of tasks that have been saved',
    'saving_finished': 'All files are saved.',
    'unknown_columns': 'Unknown columns are ignored.'
}


def compose_message_field_errors(errors, ind):
    message = 'Row {} is impossible to save. Errors in fields:\n{}\n'.format(ind, errors)
    return message


class OrderCSVMapperMixin(object):
    serializer = CSVOrderSerializer()

    @property
    def unknown_columns(self):
        return self.field_validators[HeaderControl].unknown_fields

    @property
    def optional_missing(self):
        return self.field_validators[HeaderControl].optional_missing


class OrderCSVMapper(OrderCSVMapperMixin, PandasReadMapper):
    pass


class OrderUnicodeCSVMapper(OrderCSVMapperMixin, UnicodeCSVReadMapper):
    pass


class OrderCSVParser(CSVModelMappingReader):
    mapper_class = OrderCSVMapper
    backend = PandasCSVBackend()


class OrderUnicodeCSVParser(CSVModelMappingReader):
    backend = UnicodeCSVReadBackend()
    mapper_class = OrderUnicodeCSVMapper


class AdditionalFieldsFilter(mappers.BaseFilter):
    @property
    def add_columns(self):
        return self._add_columns

    def __init__(self, mapper):
        super(AdditionalFieldsFilter, self).__init__(mapper)
        self._add_columns = list(Order.objects.all().dates_for_csv().values())

    def filter(self, value):
        event_stats = value.pick_events_for_csv()
        df_2 = pd.DataFrame.from_dict(event_stats, orient='index', columns=self.add_columns)
        return df_2


class SurveyResultsFieldsFilter(mappers.BaseFilter):

    def filter(self, value):
        index_column = self._mapper.index_col
        customer_survey_results = value.values(index_column, self._mapper.survey_field_name)
        df_2 = json_normalize(customer_survey_results or [])
        if not df_2.empty:
            df_2 = df_2.set_index(index_column)
        return df_2


class ShortcutLinksFilter(mappers.BaseFilter):

    def filter(self, value):
        if not self._mapper.context['shorten_report_url']:
            return value

        urls = [url for url in value['full_report_url'] if url]
        short_urls = shortcut_link_safe(urls, many=True)
        for index, url in value['full_report_url'].items():
            if url:
                value.at[index, 'full_report_url'] = short_urls.get(url, url)
        return value


class OrderCSVWriteMapper(QuerySetChunkMapper):
    """
    All instances of parsers share the same mapper and backend, so it's important not to store any
    cached context or another data.
    """
    serializer = CSVOrderReportSerializer()

    class ContextWriteMapper(mappers.FlowMapper):
        filter_flow = (AdditionalFieldsFilter, FormatDateDataFrameFilter, )

        def __init__(self, context, mapper):
            self.mapper = mapper
            self.context = context
            self.index_col = mapper.index_col
            super(OrderCSVWriteMapper.ContextWriteMapper, self).__init__()

        @property
        def date_fields(self):
            return {
                'columns': self.basic_flow[0].add_columns,
                'formats': {k: self.context['date_format'] for k in self.basic_flow[0].add_columns}
            }

        @property
        def timezone(self):
            return self.context['timezone']

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def __call__(self, value):
            df_2 = super(OrderCSVWriteMapper.ContextWriteMapper, self).__call__(value)
            df = self.mapper(value)
            df = ShortcutLinksFilter(self).filter(df)
            return df.join(df_2)

    def using_context(self, context):
        return self.ContextWriteMapper(context, self)


class ExtendedOrderCSVWriteMapper(OrderCSVWriteMapper):

    serializer = ExtendedCSVOrderReportSerializer()

    class ExtendedContextWriteMapper(OrderCSVWriteMapper.ContextWriteMapper):
        filter_flow = (SurveyResultsFieldsFilter, )

        @property
        def survey_field_name(self):
            return self.context['survey_field_name']

    def using_context(self, context):
        mapper = super(ExtendedOrderCSVWriteMapper, self).using_context(context)
        return self.ExtendedContextWriteMapper(context, mapper)


class OrderQSWriter(QuerySetChunkMappingWriter):
    queryset = Order.objects
    mapper_class = OrderCSVWriteMapper
    backend = PandasWritingCSVBackend()

    _date_formats = {
        Merchant.LITTLE_ENDIAN: {'python': '%d/%m/%Y %X', 'psql': 'DD/MM/YYYY HH24:MI:SS'},
        Merchant.MIDDLE_ENDIAN: {'python': '%m/%d/%Y %X', 'psql': 'MM/DD/YYYY HH24:MI:SS'},
        Merchant.BIG_ENDIAN: {'python': '%Y-%m-%d %X', 'psql': 'YYYY-MM-DD HH24:MI:SS'}
    }

    @cached_property
    def timezone(self):
        return str(self.merchant.timezone) if self.merchant else settings.TIME_ZONE

    @cached_property
    def date_format(self):
        return self.merchant.date_format if self.merchant else settings.DEFAULT_DATE_FORMAT

    @cached_property
    def shorten_report_url(self):
        return self.merchant.shorten_report_url if self.merchant else False

    def get_queryset(self):
        qs = self.queryset.for_csv(
            tz=self.timezone,
            date_format=self._date_formats[self.date_format]['psql'],
            **self.filter_params
        )
        return self.mapper.update_qs(qs)

    @property
    def mapper_context(self):
        return {
            'date_format': self._date_formats[self.date_format]['python'],
            'timezone': self.timezone,
            'shorten_report_url': self.shorten_report_url,
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
        super(OrderQSWriter, self).__init__(model_obj, **kwargs)


class SurveyResultsQSWriter(OrderQSWriter):
    mapper_class = ExtendedOrderCSVWriteMapper

    def __init__(self, model_obj, params, **kwargs):
        self.survey_field_name = 'survey_results'
        survey = params.get('survey')
        self.report_extra_fields = [
            "{}.{}".format(self.survey_field_name, question) for question in survey.questions_text
        ]
        super(SurveyResultsQSWriter, self).__init__(model_obj, params, **kwargs)

    def _initialize_mapper(self):
        return self.mapper_class(extra_fields=self.report_extra_fields)

    @property
    def mapper_context(self):
        context = super(SurveyResultsQSWriter, self).mapper_context
        context['survey_field_name'] = self.survey_field_name
        return context
