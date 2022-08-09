from ..const import EventType
from ..registry import log_item_registry
from .base import LogItem


class ProgressConst:
    # Optimisation related
    START = 'start'
    CLUSTERING = 'clusters'
    ENGINES_CREATE = 'eng_create'
    ASSIGN = 'assign'
    FINISH = 'finish'

    # Engine related
    START_DISTANCE_MATRIX = 'start_dima'
    DISTANCE_MATRIX = 'dima'
    ALGORITHM = 'alg'
    ENGINE_FINISH = 'eng_finish'


@log_item_registry.register()
class ProgressLog(LogItem):
    event = EventType.PROGRESS

    def write_in_log(self, optimisation_log, labels):
        from route_optimisation.models import EngineRun, RouteOptimisation
        if isinstance(self.log_subject, RouteOptimisation):
            self._write_in_optimisation_log(optimisation_log)
        elif isinstance(self.log_subject, EngineRun):
            self._write_in_engine_run_log(optimisation_log)

    def _write_in_engine_run_log(self, optimisation_log):
        stage = self.event_kwargs.get('stage')
        progress = 0
        if stage == ProgressConst.START_DISTANCE_MATRIX:
            progress = 5
        elif stage == ProgressConst.DISTANCE_MATRIX:
            progress = 20
        elif stage == ProgressConst.ALGORITHM:
            num, count = self.event_kwargs.get('num'), self.event_kwargs.get('count')
            progress = 20 + int((num/count) * 80)
        elif stage == ProgressConst.ENGINE_FINISH:
            progress = 100
        optimisation_log['last_stage'] = stage or optimisation_log.get('last_stage')
        optimisation_log['progress'] = min(100, max(optimisation_log.get('progress', 0), progress))

    def _write_in_optimisation_log(self, optimisation_log):
        if 'engine_run_state' in self.event_kwargs:
            engines = optimisation_log.get('engines')
            if engines is None:
                self._handle_when_no_splitting(optimisation_log)
            else:
                self._handle_when_several_engine_runs(optimisation_log, engines)
        else:
            self._handle_optimisation_stage(optimisation_log)

    def _handle_when_no_splitting(self, optimisation_log):
        stage = self.event_kwargs.get('stage')
        steps = optimisation_log.get('steps', [])
        progress = 0
        if stage == ProgressConst.START_DISTANCE_MATRIX:
            progress = 5
            for step in steps:
                step['completed'] = True
            steps.append({'name': 'Composing the distance matrix', 'completed': False})
        elif stage == ProgressConst.DISTANCE_MATRIX:
            for step in steps:
                step['completed'] = True
            steps.append({'name': 'Looking for the optimum routes', 'completed': False})
            progress = 10
        elif stage == ProgressConst.ALGORITHM:
            num, count = self.event_kwargs.get('num'), self.event_kwargs.get('count')
            progress = 10 + int((num / count) * 80)
        elif stage == ProgressConst.ENGINE_FINISH:
            progress = 90
        optimisation_log['steps'] = steps
        optimisation_log['progress'] = min(100, max(optimisation_log.get('progress', 0), progress))

    def _handle_when_several_engine_runs(self, optimisation_log, engines):
        steps = optimisation_log.get('steps', [])
        progress, max_progress = 0, len(engines) * 100

        current_engine_state = self.event_kwargs['engine_run_state']
        engine_id = current_engine_state['engine_id']
        current_engine = engines.get(engine_id, engines.get(str(engine_id)))
        current_engine['progress'] = current_engine_state['progress']
        sum_progress = sum(e['progress'] for e in engines.values())
        progress = 10 + int((sum_progress/max_progress)*80)

        optimisation_log['engines'] = engines
        optimisation_log['steps'] = steps
        optimisation_log['progress'] = min(100, max(optimisation_log.get('progress', 0), progress))

    def _handle_optimisation_stage(self, optimisation_log):
        stage = self.event_kwargs.get('stage')
        progress = 0
        steps = optimisation_log.get('steps', [])
        if stage == ProgressConst.START:
            progress = 0
        elif stage == ProgressConst.CLUSTERING:
            progress = 5
            for step in steps:
                step['completed'] = True
            steps.append({'name': 'Splitting jobs into groups', 'completed': False})
        elif stage == ProgressConst.ENGINES_CREATE:
            progress = 10
            optimisation_log['engines'] = self.event_kwargs.get('engines')
            for step in steps:
                step['completed'] = True
            steps.append({'name': 'Looking for the optimum routes', 'completed': False})
        elif stage == ProgressConst.ASSIGN:
            assign_percent = self.event_kwargs.get('assign_percent', None)
            if assign_percent is None:
                for step in steps:
                    step['completed'] = True
                steps.append({'name': 'Assigning jobs between the drivers', 'completed': False})
            progress = 90 + int((assign_percent or 0) / 10)
        elif stage == ProgressConst.FINISH:
            success = self.event_kwargs.get('success')
            if success:
                for step in steps:
                    step['completed'] = True
            progress = 100
        optimisation_log['steps'] = steps
        optimisation_log['progress'] = min(100, max(optimisation_log.get('progress', 0), progress))

    @classmethod
    def build_message(cls, item, *args, **kwargs):
        pass
