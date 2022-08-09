import copy

from django.db.models import Sum
from django.utils import timezone

try:
    from delivery.settings.ansible.env_vars import ERROR_EMAIL_PREFIX
except ImportError:
    ERROR_EMAIL_PREFIX = 'RADARO DEV'

DATE_FORMAT = '%b %d'
WEEKLY_CONTEXT = {
    'server_name': ERROR_EMAIL_PREFIX,
    'report_period': '',
    'types': ['merchants', 'jobs', 'drivers'],
    'detailed_types': ['jobs', 'drivers'],
    'data': None,
    'preferences': {
        'jobs': {
            'table_verbose': 'Jobs Per Merchant',
            'total_verbose': 'Total Jobs Created',
            'min_count': 3,
            'note': 'Active Merchants - merchants who have created more than 3 jobs during the last 7 days',
            'compare_with_prev': True
        },
        'drivers': {
            'table_verbose': 'Active Drivers',
            'total_verbose': 'Active Drivers',
            'min_count': 1,
            'note': 'Active Drivers - drivers who have used Radaro at least once during the last 7 days',
            'compare_with_prev': False
        },
        'merchants': {
            'total_verbose': 'Active Merchants',
            'compare_with_prev': True
        }
    },
    'body_width': '595px',
    'content_width': '537px'
}
WEEKLY_CONTEXT_DATA = {
    'total': {
        'merchants': {'count': 0, 'previous_count': 0},
        'jobs': {'count': 0, 'previous_count': 0},
        'drivers': {'count': 0},
    },
    'detailed': {
        'jobs': None,
        'drivers': None
    }
}


def weekly_usage_context(report_date):
    from merchant.models import Merchant

    def calculate_percents(item):
        return (item['count'] - item['previous_count']) * 100 / item['previous_count'] if item['previous_count'] \
            else None

    week_ago = report_date - timezone.timedelta(weeks=1)
    two_weeks_ago = report_date - timezone.timedelta(weeks=2)

    current_period = {
        'from': week_ago,
        'to': report_date
    }
    previous_period = {
        'from': two_weeks_ago,
        'to': week_ago
    }

    context = copy.copy(WEEKLY_CONTEXT)
    context['report_period'] = '%s - %s' % (current_period['from'].strftime(DATE_FORMAT),
                                            (current_period['to'] - timezone.timedelta(days=1)).strftime(DATE_FORMAT))

    report_data = copy.deepcopy(WEEKLY_CONTEXT_DATA)

    for key in context['detailed_types']:
        preferences = context['preferences'][key]
        args = [current_period, previous_period] if preferences['compare_with_prev'] else [current_period, ]
        report = getattr(Merchant.objects, key + '_usage_report')(*args)
        total = report_data['total'][key]
        for field in total:
            total[field] = report.aggregate(sum=Sum(field))['sum']
        if preferences['compare_with_prev']:
            total['percent_growth'] = calculate_percents(total)
        report_data['detailed'][key] = list(report.filter(count__gte=preferences['min_count']))
        if key == 'jobs':
            merchants = report_data['total']['merchants']
            merchants['count'] = len(report_data['detailed']['jobs'])
            merchants['previous_count'] = report.filter(previous_count__gte=preferences['min_count']).count()
            merchants['percent_growth'] = calculate_percents(merchants)

    context['data'] = report_data
    return context
