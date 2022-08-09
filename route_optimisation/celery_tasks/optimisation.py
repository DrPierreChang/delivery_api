import logging
import random
import time
from typing import List

from celery.exceptions import SoftTimeLimitExceeded

from base.models import Member
from delivery.celery import app
from reporting.signals import create_event
from route_optimisation.const import OPTIMISATION_TYPES
from route_optimisation.dima import RadaroDimaCache
from route_optimisation.engine import Algorithms, EngineParameters, ROError
from route_optimisation.engine.base_classes.result import AssignmentResult
from route_optimisation.exceptions import OptimisationValidError
from route_optimisation.intelligent_clustering import Clustering
from route_optimisation.intelligent_clustering.big_clusters import BigClustersManager
from route_optimisation.logging import EventType, move_dummy_optimisation_log
from route_optimisation.logging.logs.progress import ProgressConst
from route_optimisation.models import EngineRun, OptimisationTask, RefreshDummyOptimisation, RouteOptimisation
from route_optimisation.models.engine_run import EngineOptions
from route_optimisation.optimisation_events import RadaroEventsHandler
from routing.google import GoogleClient

logger = logging.getLogger('optimisation')


def separate_groups(optimisation) -> List[EngineParameters]:
    with GoogleClient.track_merchant(optimisation.merchant):
        clustering = Clustering(
            optimisation.backend.get_params_for_engine(),
            event_handler=RadaroEventsHandler(optimisation),
            distance_matrix_cache=RadaroDimaCache()
        )
        try:
            clustering.run(steps_count=20)
            return clustering.clustered_params
        finally:
            optimisation.backend.track_api_requests_stat(clustering.api_requests_tracker)


def get_exception_dict_for_combined_result(exception_dicts):
    filtered_dicts = list(filter(
        lambda exc_dict: issubclass(exc_dict['exc_class'], (OptimisationValidError, ROError)),
        exception_dicts
    ))
    if filtered_dicts:
        return filtered_dicts[0]
    filtered_dicts = list(filter(
        lambda exc_dict: issubclass(exc_dict['exc_class'], SoftTimeLimitExceeded),
        exception_dicts
    ))
    if filtered_dicts:
        return filtered_dicts[0]
    return exception_dicts[0]


def combine_engine_run_results(engine_runs):
    tours = {}
    driving_distance, driving_time = 0, 0
    good = False
    skipped_orders, skipped_drivers, exception_dicts = [], set(), []
    for engine_run in engine_runs:
        result: AssignmentResult = engine_run.result
        if result.good:
            good = True
            tours.update(result.drivers_tours)
            skipped_orders.extend(result.skipped_orders)
            skipped_drivers.update(result.skipped_drivers)
            driving_distance += result.driving_distance
            driving_time += result.driving_time
        else:
            skipped_orders.extend([order.id for order in engine_run.engine_options.params.jobs])
            skipped_drivers.update(set([driver.member_id for driver in engine_run.engine_options.params.drivers]))
            exception_dicts.append(result.exception_dict)
    if good:
        return AssignmentResult(tours, skipped_orders, driving_time, driving_distance, skipped_drivers, good)
    return AssignmentResult(
        None, None, None, None, None, good=False,
        exception_dict=get_exception_dict_for_combined_result(exception_dicts),
    )


def is_small_optimisation(optimisation):
    if optimisation.type == OPTIMISATION_TYPES.SOLO:
        return True
    params = optimisation.backend.get_params_for_engine()
    big_clusters_count = BigClustersManager.calc_clusters_count(params.jobs, params.drivers)
    return big_clusters_count == 1


def run_optimisation(task, optimisation):
    task_id = task.register_delayed_task()
    if is_small_optimisation(optimisation):
        run_small_optimisation.apply_async((task.id,), task_id=task_id)
    else:
        run_advanced_optimisation.apply_async((task.id,), task_id=task_id)


@app.task(soft_time_limit=3000, time_limit=3300)
def run_small_optimisation(task_id):
    task = OptimisationTask.objects.get(id=task_id)
    optimisation = task.optimisation
    optimisation.state_to(RouteOptimisation.STATE.OPTIMISING)
    task.event('Start', OptimisationTask.INFO, OptimisationTask.IN_PROGRESS)
    Runner.run(task, optimisation)


@app.task(soft_time_limit=3000, time_limit=3300)
def run_advanced_optimisation(task_id):
    task = OptimisationTask.objects.get(id=task_id)
    optimisation = task.optimisation
    optimisation.state_to(RouteOptimisation.STATE.OPTIMISING)
    task.event('Start', OptimisationTask.INFO, OptimisationTask.IN_PROGRESS)
    AdvancedRunner.run(task, optimisation)


@app.task(soft_time_limit=3000, time_limit=3300)
def optimisation_engine_run(engine_run_id):
    engine_run = EngineRun.objects.get(id=engine_run_id)
    try:
        engine_run.run_engine()
    finally:
        handle_results.delay(engine_run_id)


@app.task(soft_time_limit=3000, time_limit=3300)
def handle_results(engine_run_id):
    engine_run = EngineRun.objects.get(id=engine_run_id)
    optimisation = engine_run.optimisation
    active_runs = optimisation.engine_runs.all().filter(state__in=EngineRun.calculating).count()
    if active_runs > 0 and not optimisation.is_terminated:
        return

    task = optimisation.delayed_task
    # In case more than one handle_results tasks running at the same time.
    # AdvancedRunner.handle_results() have to run only once.
    time.sleep(random.random() * 5)
    key = f'handle-results-optimisation-{optimisation.id}'
    if task.cache.get(key) is True:
        return
    task.cache.set(key, True, timeout=300)

    AdvancedRunner.handle_results(task, optimisation)


class RunnerBase:
    @staticmethod
    def get_pp_distance_matrix_cache():
        return RadaroDimaCache(polylines=True)


class AdvancedRunner(RunnerBase):
    @staticmethod
    def run(task, optimisation):
        try:

            logger.info(None, extra=dict(obj=optimisation, event=EventType.PROGRESS,
                                         event_kwargs=dict(stage=ProgressConst.START), labels=[], ))
            groups = separate_groups(optimisation)
            logger.info(None, extra=dict(obj=optimisation, event=EventType.PROGRESS,
                                         event_kwargs=dict(stage=ProgressConst.CLUSTERING), labels=[], ))

            engine_runs = []
            for group_params in groups:
                options = EngineOptions(
                    params=group_params,
                    algorithm=optimisation.backend.algorithm_name
                )
                engine_runs.append(EngineRun.objects.create(optimisation=optimisation, engine_options=options))
            log_engines = {engine_run.id: {'progress': 0} for engine_run in engine_runs}
            logger.info(None, extra=dict(obj=optimisation, event=EventType.PROGRESS,
                                         event_kwargs=dict(stage=ProgressConst.ENGINES_CREATE, engines=log_engines),
                                         labels=[], ))
            for engine_run in engine_runs:
                task_id = task.register_delayed_task()
                optimisation_engine_run.apply_async((engine_run.id,), task_id=task_id)

        except Exception as exc:
            optimisation.backend.on_fail(exception=exc)
            logger.info(None, extra=dict(obj=optimisation, event=EventType.PROGRESS,
                                         event_kwargs=dict(stage=ProgressConst.FINISH, success=False), labels=[], ))
            task.complete()
            task.save(update_fields=('status',))

    @staticmethod
    def handle_results(task, optimisation):
        success = False
        try:
            if optimisation.is_terminated:
                optimisation.backend.on_fail()
                return
            success = AdvancedRunner.on_all_engine_runs_completed(optimisation)
        except Exception as exc:
            optimisation.backend.on_fail(exception=exc)
        finally:
            logger.info(None, extra=dict(obj=optimisation, event=EventType.PROGRESS,
                                         event_kwargs=dict(stage=ProgressConst.FINISH, success=success), labels=[], ))
            task.complete()
            task.save(update_fields=('status',))

    @staticmethod
    def on_all_engine_runs_completed(optimisation):
        engine_runs = list(optimisation.engine_runs.all())
        result = combine_engine_run_results(engine_runs)
        if result.good:
            optimisation.backend.post_processing(
                result, distance_matrix_cache=AdvancedRunner.get_pp_distance_matrix_cache()
            )
            optimisation.backend.on_finish(result)
        else:
            optimisation.backend.on_fail(engine_result=result)
        return result.good


class Runner(RunnerBase):
    @staticmethod
    def run(task, optimisation):
        success = False
        try:
            logger.info(None, extra=dict(obj=optimisation, event=EventType.PROGRESS,
                                         event_kwargs=dict(stage=ProgressConst.START), labels=[], ))
            result = Runner.run_engine(optimisation)
            success = result.good
            if success:
                optimisation.backend.post_processing(
                    result, distance_matrix_cache=Runner.get_pp_distance_matrix_cache()
                )
                optimisation.backend.on_finish(result)
            else:
                optimisation.backend.on_fail(engine_result=result)
        except Exception as exc:
            optimisation.backend.on_fail(exception=exc)
        finally:
            logger.info(None, extra=dict(obj=optimisation, event=EventType.PROGRESS,
                                         event_kwargs=dict(stage=ProgressConst.FINISH, success=success), labels=[], ))
            task.complete()
            task.save(update_fields=('status',))

    @staticmethod
    def run_engine(optimisation):
        options = EngineOptions(
            params=optimisation.backend.get_params_for_engine(),
            algorithm=optimisation.backend.algorithm_name
        )
        engine_run = EngineRun.objects.create(optimisation=optimisation, engine_options=options)
        return engine_run.run_engine()


@app.task(soft_time_limit=3000, time_limit=3300)
def run_optimisation_refresh(optimisation_id, optimisation_options, initiator_id):
    optimisation = RouteOptimisation.objects.get(id=optimisation_id)
    RefreshRunner.run(optimisation, optimisation_options, initiator_id)


class RefreshRunner(RunnerBase):
    @staticmethod
    def run(optimisation, optimisation_options, initiator_id):
        initiator = Member.objects.get(id=initiator_id)
        engine, success = None, False
        dummy_optimisation = RefreshDummyOptimisation(
            optimisation,  optimisation.day, optimisation.merchant,
            initiator, backend_name=optimisation.backend.refresh_backend_name
        )
        dummy_optimisation.state_to(RouteOptimisation.STATE.OPTIMISING)
        dummy_optimisation.optimisation_options = optimisation_options
        try:
            logger.info(None, extra=dict(obj=dummy_optimisation, event=EventType.PROGRESS,
                                         event_kwargs=dict(stage=ProgressConst.START), labels=[], ))
            result = RefreshRunner.engine_run(optimisation, dummy_optimisation)
            success = result.good
            if success:
                dummy_optimisation.backend.post_processing(
                    result, distance_matrix_cache=RefreshRunner.get_pp_distance_matrix_cache()
                )
                dummy_optimisation.backend.on_finish(result)
            else:
                dummy_optimisation.backend.on_fail(engine_result=result)
        except Exception as exc:
            dummy_optimisation.backend.on_fail(exception=exc)
        finally:
            logger.info(None, extra=dict(obj=dummy_optimisation, event=EventType.PROGRESS,
                                         event_kwargs=dict(stage=ProgressConst.FINISH, success=success), labels=[], ))
            move_dummy_optimisation_log(dummy_optimisation, optimisation, dev=False)
            create_event({}, {}, initiator=initiator, instance=optimisation, sender=None, force_create=True)

    @staticmethod
    def engine_run(optimisation, dummy_optimisation):
        options = EngineOptions(
            params=dummy_optimisation.backend.get_params_for_engine(),
            algorithm=Algorithms.ONE_DRIVER
        )
        engine_run = EngineRun.objects.create(optimisation=optimisation, engine_options=options)
        engine_run.dummy_optimisation = dummy_optimisation
        return engine_run.run_engine()


@app.task(soft_time_limit=600, time_limit=700)
def delete_optimisation(optimisation_id, unassign, initiator_id):
    optimisation = RouteOptimisation.objects.get(id=optimisation_id)
    initiator = Member.objects.get(id=initiator_id)
    optimisation.delete(initiator=initiator, unassign=unassign)
