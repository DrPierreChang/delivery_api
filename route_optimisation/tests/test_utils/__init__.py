import json
from datetime import time

from dateutil.parser import parse

from base.models import Car, Member
from merchant.models import Hub, HubLocation
from route_optimisation.celery_tasks.optimisation import combine_engine_run_results
from route_optimisation.models import EngineRun
from schedule.models import Schedule
from tasks.models import Customer, Order, OrderLocation


def dump_ro_results(optimisation_id, name):
    result = combine_engine_run_results(EngineRun.objects.filter(optimisation_id=optimisation_id))
    res = []
    for dr, tour in result.drivers_tours.items():
        points = []
        for point in tour.points:
            points.append({'kind': point.point_kind, 'loc': point.location})
        res.append({'driver_id': dr, 'points': points})
    with open(f'result_replays/{name}.json', 'w') as f:
        json.dump({'routes': res}, f)


def create_from_engine_options(file_name, merchant_id, manager_id):
    # file_name = '../ro-clustering/ro_clusters/show-ro/src/assets/prod_case_s5_opt....._options.json'
    # merchant_id = 18100
    # manager_id = ?

    with open(file_name) as f:
        data = json.load(f)

    hubs_map = {}
    driver_map = {}
    for i, dr in enumerate(data['drivers']):
        if dr['start_hub']['id'] not in hubs_map:
            hubs_map[dr['start_hub']['id']] = Hub.objects.create(
                name=f'Heavy Sydney {len(hubs_map)}', merchant_id=merchant_id,
                location=HubLocation.objects.create(
                    location=dr['start_hub']['location'],
                    address=f'address sydney {len(hubs_map)}'
                )
            ).id
        if dr['end_hub']['id'] not in hubs_map:
            hubs_map[dr['end_hub']['id']] = Hub.objects.create(
                name=f'Heavy Sydney {len(hubs_map)}', merchant_id=merchant_id,
                location=HubLocation.objects.create(
                    location=dr['end_hub']['location'],
                    address=f'address sydney {len(hubs_map)}'
                )
            ).id
        driver = Member.objects.create(
            member_id=dr['member_id'], merchant_id=merchant_id, car=Car.objects.create(capacity=dr['capacity']),
            role=Member.DRIVER, starting_hub_id=hubs_map[dr['start_hub']['id']],
            ending_hub_id=hubs_map[dr['end_hub']['id']], username=f'heavysydney{i}', email=f'heavy{i}@sydney.com',
            phone=f'+61436{str(111200+i)}', first_name='Heavy', last_name=f'Sydney {i}'
        )
        driver_map[dr['id']] = driver
        schedule, _ = Schedule.objects.get_or_create(member=driver)
        for wi in range(7):
            schedule.schedule['constant'][wi]['start'] = time(*list(map(int, dr['start_time'].split(':'))))
            schedule.schedule['constant'][wi]['end'] = time(*list(map(int, dr['end_time'].split(':'))))
            schedule.schedule['constant'][wi]['day_off'] = False
        schedule.save(update_fields=('schedule',))

    orders_map = {}
    for ji, jj in enumerate(data['jobs']):
        order = Order.objects.create(
            title=f'Heavy job sydney {ji}', capacity=jj['capacity'],
            driver_id=Member.objects.get(member_id=jj['driver_member_id']) if jj['driver_member_id'] else None,
            manager_id=manager_id, merchant_id=merchant_id,
            deliver_address=OrderLocation.objects.create(
                location=jj['deliver_address'], address=f'{jj["deliver_address"]} {ji}-3'
            ),
            deliver_after=parse(jj['deliver_after']).replace(day=13, month=7, year=2022)
            if jj['deliver_after'] else None,
            deliver_before=parse(jj['deliver_before']).replace(day=13, month=7, year=2022),
            status=Order.NOT_ASSIGNED if jj['driver_member_id'] is None else Order.ASSIGNED,
            customer=Customer.objects.create(name=f'Customer order heavy job {ji}-3')
        )
        orders_map[jj['id']] = order

    return hubs_map, driver_map, orders_map
