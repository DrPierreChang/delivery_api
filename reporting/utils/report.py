import copy
from datetime import timedelta

from reporting.api.legacy.serializers.serializers import OrderParametersSerializer


def fill_data_and_sum(data, dates, accum):
    prototype = copy.copy(accum)
    result = []
    date_from = dates['date_from'].replace(tzinfo=None)
    date_to = dates['date_to'].replace(tzinfo=None)
    while date_from < date_to:
        current_date = date_from.strftime('%Y-%m-%d')
        items_for_date = [data_item for data_item in data if current_date == data_item['date']]
        if items_for_date:
            item = items_for_date[0]
            result.append(item)
            for key in accum.keys():
                accum[key] += (item[key] or 0)
        else:
            obj = copy.copy(prototype)
            obj['date'] = current_date
            result.append(obj)
        date_from += timedelta(days=1)
    return result


def get_request_params(request):
    parameters_serializer = OrderParametersSerializer(data=request.query_params, context={'request': request})
    parameters_serializer.is_valid(raise_exception=True)
    return parameters_serializer.validated_data
