from datetime import timedelta


def filter_from_indexes(array, indexes):
    return [array[i] for i in indexes]


def to_dict_point(y, x=None, x_y=True):
    if x is None and isinstance(y, str):
        y, x = list(map(str.strip, list(map(str, y.split(',')))))

    mas = ['y', 'x'] if x_y else ['lat', 'lng']
    return dict(zip(mas, [y, x]))


def datetime_to_day_seconds(datetime_obj):
    t = datetime_obj.time()
    return int(timedelta(hours=t.hour, minutes=t.minute, seconds=t.second).total_seconds())


def time_to_seconds(time_str):
    time_parts = list(map(int, list(map(float, time_str.split(':')))))
    return int(timedelta(hours=time_parts[0], minutes=time_parts[1], seconds=time_parts[2]).total_seconds())
