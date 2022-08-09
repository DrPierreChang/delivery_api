import functools
import operator
import uuid

from django.db import models
from django.http import HttpResponse, HttpResponseBadRequest
from django.urls import reverse

import pandas as pd

from notification.models import GCMDevice
from radaro_utils.utils import get_date_format
from radaro_utils.views import GenericTimeFramedReport

from .forms import DeviceVersionReportForm


class Column(object):
    def __init__(self, name, field, use_in_grouping=False, searchable=False, ordering=False, detailed=False):
        self.name = name
        self.field = field
        self.detailed = detailed
        self.use_in_grouping = use_in_grouping
        self.ordering = ordering
        self.searchable = searchable
        self.params = None

    @staticmethod
    def filter_by_use_in_grouping(columns):
        return map(operator.attrgetter('field'), filter(operator.attrgetter('use_in_grouping'), columns))

    @staticmethod
    def filter_by_searchable(columns):
        return map(operator.attrgetter('field'), filter(operator.attrgetter('searchable'), columns))

    def build_ordering_url(self, **kwargs):
        params = dict(self.params, **kwargs)
        return '?%s' % '&'.join(['{}={}'.format(k, v) for k, v in params.items()])

    @property
    def ordering_type(self):
        ordering = self.params.get('ordering', '')
        has_ordering = ordering.endswith(self.field)
        if has_ordering:
            return DeviceVersionReportBase.ORDERING_DESC \
                if ordering.startswith('-') \
                else DeviceVersionReportBase.ORDERING_ASC
        return ''

    @property
    def ordering_remove(self):
        return self.build_ordering_url(ordering=DeviceVersionReportBase.ORDERING_DISABLED)

    @property
    def ordering_toggle(self):
        if self.ordering_type == DeviceVersionReportBase.ORDERING_DESC:
            ord_toggle = ''
        else:
            ord_toggle = '-'
        return self.build_ordering_url(ordering='%s%s' % (ord_toggle, self.field))


class DeviceVersionReportBase(GenericTimeFramedReport):
    ORDERING_DISABLED = ''
    ORDERING_ASC = 'ascending'
    ORDERING_DESC = 'descending'

    columns = [
        Column('OS Type', 'device_type', use_in_grouping=True, searchable=True),
        Column('App Version', 'app_version', ordering=True, use_in_grouping=True, searchable=True),
        Column('Merchant ID', 'user__merchant_id', detailed=True, use_in_grouping=True),
        Column('Merchant Name', 'user__merchant__name', detailed=True, use_in_grouping=True, searchable=True),
        Column('Number of devices', 'num', ordering=True),
    ]

    def __init__(self, **kwargs):
        self.report_type = None
        self.ordering = self.ORDERING_DISABLED
        self.search_query = ''
        self.app_name = None
        self.form = None
        super(DeviceVersionReportBase, self).__init__(**kwargs)

    @property
    def report_type_columns(self):
        return filter(lambda x: not x.detailed or self.is_detailed_report, self.columns)

    def dispatch(self, request, *args, **kwargs):
        self.search_query = request.GET.get('q', '')
        self.report_type = request.GET.get('report_type', DeviceVersionReportForm.SHORT_REPORT)
        self.ordering = request.GET.get('ordering', self.ORDERING_DISABLED)
        self.app_name = request.GET.get('app_name', '')
        return super(DeviceVersionReportBase, self).dispatch(request, *args, **kwargs)

    def clean_form(self):
        date_format = get_date_format()
        self.form = DeviceVersionReportForm(data={
            'date_from': self.date_from.strftime(date_format),
            'date_to': self.date_to.strftime(date_format),
            'report_type': self.report_type,
            'app_name': self.app_name,
        })
        if self.form.is_valid():
            self.date_from = self.form.cleaned_data.get('date_from')
            self.date_to = self.form.cleaned_data.get('date_to')
            self.report_type = self.form.cleaned_data.get('report_type')
            self.app_name = self.form.cleaned_data.get('app_name')
        query_params = dict(self.request.GET.items())
        for column in self.columns:
            column.params = query_params

    @property
    def table_content(self):
        qs = GCMDevice.objects \
            .filter(
                user__isnull=False, user__merchant__isnull=False,
                user__last_ping__date__gte=self.date_from, user__last_ping__date__lte=self.date_to,
                app_version__isnull=False, in_use=True,
            )
        for transform_qs in [self._grouping, self._ordering, self._filtering, self._search]:
            qs = transform_qs(qs)
        return qs

    def _grouping(self, qs):
        grouping_by = list(Column.filter_by_use_in_grouping(self.report_type_columns))
        return qs \
            .order_by(*grouping_by) \
            .values(*grouping_by) \
            .annotate(num=models.Count('id'))

    def _ordering(self, qs):
        final_ordering = ('device_type', 'app_version', '-num')
        for column in self.columns:
            if column.ordering_type != '':
                ordering_sign = '-' if column.ordering_type == self.ORDERING_DESC else ''
                final_ordering = ['{sign}{field}'.format(sign=ordering_sign, field=column.field)]
                break
        return qs.order_by(*final_ordering)

    def _filtering(self, qs):
        if self.app_name:
            return qs.filter(app_name=self.app_name)
        return qs

    def _search(self, qs):
        if not self.search_query:
            return qs
        search_fields = list(Column.filter_by_searchable(self.report_type_columns))
        for bit in self.search_query.split():
            or_queries = [models.Q(**{"%s__icontains" % field: bit}) for field in search_fields]
            cond = functools.reduce(operator.or_, or_queries)
            qs = qs.filter(cond)
        return qs

    @property
    def is_detailed_report(self):
        return self.report_type == DeviceVersionReportForm.DETAILED_REPORT


class DeviceVersionReportView(DeviceVersionReportBase):
    template_name = 'notification/device_versions.html'

    def get_context_data(self, **kwargs):
        self.clean_form()
        ctx = super(DeviceVersionReportView, self).get_context_data(**kwargs)
        ctx.update({
            'form': self.form,
            'items': self.table_content,
            'is_detailed_report': self.is_detailed_report,
            'ordering': self.ordering,
            'search_query': self.search_query,
            'csv_url': self.build_generate_csv_url(),
            'enable_csv_url': self.table_content.exists(),
            'columns': self.columns,
        })
        return ctx

    def build_generate_csv_url(self):
        tmpl = '{base}?date_from={d_from}&date_to={d_to}&report_type={rep_type}&q={query}&ordering={ord}' \
               '&app_name={a_name}'
        return tmpl.format(
            base=reverse('admin:cms-device-versions-csv'),
            d_from=self.form.data['date_from'],
            d_to=self.form.data['date_to'],
            rep_type=self.report_type,
            query=self.search_query,
            ord=self.ordering,
            a_name=self.app_name,
        )


class CSVDeviceVersionReportView(DeviceVersionReportBase):
    def get(self, request, *args, **kwargs):
        self.clean_form()
        dataframe = self.dataframe
        if dataframe.empty:
            return HttpResponseBadRequest()
        csv_result = dataframe.to_csv(index=False, columns=self.columns_names, encoding='utf-8')
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="{0}"'.format(self.filename)
        response.write(csv_result)
        return response

    @property
    def columns_names(self):
        return map(operator.attrgetter('name'), self.report_type_columns)

    @property
    def filename(self):
        date_format = get_date_format()
        return "devices_{}_{}_{}_{}_{}.csv".format(
            self.date_from.strftime(date_format),
            self.date_to.strftime(date_format),
            self.report_type,
            self.app_name,
            str(uuid.uuid4())[:10],
        )

    @property
    def dataframe(self):
        df = pd.DataFrame.from_records(self.table_content)
        df.rename(columns=self.columns_name_map, inplace=True)
        if self.is_detailed_report:
            df['Merchant ID'] = df['Merchant ID'].astype(int)
        return df

    @property
    def columns_name_map(self):
        return {column.field: column.name for column in self.columns}
