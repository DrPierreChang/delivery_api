from datetime import datetime

from django.utils import formats

from .fields import DBBreakSerializer


def one_break_to_str(one_break):
    format = '%H:%M'
    return f"{one_break['start'].strftime(format)}-{one_break['end'].strftime(format)}"


def breaks_to_str(breaks):
    if not breaks:
        return ''
    breaks_list = [one_break_to_str(one_break) for one_break in breaks]
    return ','.join(breaks_list)


def str_to_breaks(str_breaks):
    breaks = []

    if str_breaks == '':
        return breaks

    breaks_list = str_breaks.split(',')
    for start_end in breaks_list:
        if '-' in start_end:
            start, end = tuple(start_end.split('-'))
        else:
            continue

        prepared_break = {'start': start, 'end': end}
        serializer = DBBreakSerializer(data=prepared_break)
        if serializer.is_valid():
            breaks.append(serializer.validated_data)
        else:
            raise ValueError

    return sorted(breaks, key=lambda b: b['start'])


available_time_formats = formats.get_format('TIME_INPUT_FORMATS')


def str_to_time(str_time):
    for time_format in available_time_formats:
        try:
            return datetime.strptime(str_time, time_format).time()
        except (ValueError, TypeError):
            continue
    raise ValueError()
