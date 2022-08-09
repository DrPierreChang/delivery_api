from celery.schedules import crontab
from celery.task import periodic_task

from delivery.celery import app
from radaro_router.models import RadaroRouter
from radaro_router.utils import InstanceRadaroRouterSynchronizer


@app.task(ignore_result=True)
def create_radaro_router_instance(router_id, extra):
    router = RadaroRouter.objects.get(id=router_id)
    with InstanceRadaroRouterSynchronizer(router, RadaroRouter.CREATED, extra):
        router.create_remote_instance(extra)


@app.task(ignore_result=True)
def update_radaro_router_instance(router_id, extra):
    router = RadaroRouter.objects.get(id=router_id)
    with InstanceRadaroRouterSynchronizer(router, RadaroRouter.UPDATED, extra) as router:
        router.update_remote_instance(extra)


@app.task(ignore_result=True)
def delete_radaro_router_instance(router_id, **kwargs):
    router = RadaroRouter.objects.get(id=router_id)
    with InstanceRadaroRouterSynchronizer(router, RadaroRouter.DELETED) as router:
        router.delete_remote_instance()


radaro_router_actions_map = {
    RadaroRouter.DELETED: delete_radaro_router_instance,
    RadaroRouter.CREATED: create_radaro_router_instance,
    RadaroRouter.UPDATED: update_radaro_router_instance
}


@periodic_task(run_every=crontab(minute='*/10'), ignore_result=True)
def track_unsynced_objects():
    for obj in RadaroRouter.objects.filter(synced=False):
        method = radaro_router_actions_map.get(obj.last_action)
        method.delay(obj.id, extra=obj.extra)
