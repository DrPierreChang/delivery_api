from datetime import timedelta

from django.utils import timezone


def get_the_day_started(merchant):
    time = timezone.now().astimezone(merchant.timezone)
    time -= timedelta(microseconds=1)
    return time.replace(hour=0, minute=0, second=0, microsecond=0)


def get_driver_events_over_time(driver, start_time, end_time):
    from django.contrib.contenttypes.models import ContentType

    from base.models import Member
    from reporting.models import Event

    driver_ct = ContentType.objects.get_for_model(Member)
    events = Event.objects.filter(object_id=driver.id, content_type=driver_ct, event=Event.CHANGED, field='work_status')
    events = events.prefetch_related('object')
    last_preinterval_event = events.filter(happened_at__lte=start_time).order_by('-happened_at').first()
    interval_events = events.filter(happened_at__gt=start_time, happened_at__lt=end_time).order_by('happened_at')
    return last_preinterval_event, list(interval_events)


def aggregate_driver_work_time(start_time, end_time, last_preinterval_event, interval_events):
    # Calculation of time spent in each status in the period from start_time to end_time
    from base.models import Member
    statuses = {
        status: {'start_timestamp': None, 'duration': timedelta(), 'count': 0, 'end_timestamp': None}
        for status, _ in Member.work_status_choices
    }
    old_status = None

    if last_preinterval_event:
        new_status = statuses[last_preinterval_event.new_value]
        new_status['start_timestamp'] = start_time
        new_status['count'] += 1
        new_status['end_timestamp'] = None
        old_status = new_status

    for event in interval_events:
        if old_status:
            old_status['duration'] += event.happened_at - old_status['start_timestamp']
            old_status['end_timestamp'] = event.happened_at
        new_status = statuses[event.new_value]
        new_status['start_timestamp'] = event.happened_at
        new_status['count'] += 1
        new_status['end_timestamp'] = None
        old_status = new_status

    if old_status:
        old_status['duration'] += end_time - old_status['start_timestamp']

    for item in statuses.values():
        item.pop('start_timestamp')
        if item['end_timestamp']:
            item['end_timestamp'] = timezone.now() - item['end_timestamp']

    return statuses


def get_work_status_history(events):
    history = []
    for event in events:
        location = None
        if isinstance(event.obj_dump, dict) and 'last_location' in event.obj_dump.keys():
            last_location = event.obj_dump['last_location']
            if isinstance(last_location, dict) and 'location' in last_location.keys():
                location = event.obj_dump['last_location']['location']

        history.append({
            'timestamp': event.happened_at.astimezone(event.merchant.timezone),
            'work_status': event.new_value,
            'location': location,
        })
    return history


def get_driver_statistics(driver):
    # Getting the start time of 7 day period from 00:00.
    start_time = get_the_day_started(driver.current_merchant) - timedelta(days=6)
    end_time = timezone.now()
    # Getting events within 7 days and the last event preceding them from the database
    last_preinterval_event, interval_events_7d = get_driver_events_over_time(driver, start_time, end_time)

    statuses_7d = aggregate_driver_work_time(start_time, end_time, last_preinterval_event, interval_events_7d)
    history_7d = get_work_status_history(interval_events_7d)

    # Getting the start time of 1 day period from 00:00.
    start_time = get_the_day_started(driver.current_merchant)
    # Getting events within 1 day and the last event preceding them from the previous list
    events = [last_preinterval_event] + interval_events_7d if last_preinterval_event else interval_events_7d
    last_preinterval_event = None
    interval_events_1d = []
    for event in events:
        if event.happened_at <= start_time:
            last_preinterval_event = event
        else:
            interval_events_1d.append(event)

    statuses_1d = aggregate_driver_work_time(start_time, end_time, last_preinterval_event, interval_events_1d)

    return {
        'today': {
            'time': statuses_1d,
        },
        'past_seven_days': {
            'time': statuses_7d,
            'history': history_7d,
        }
    }
