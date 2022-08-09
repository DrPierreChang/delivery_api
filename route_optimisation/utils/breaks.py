import copy
from operator import attrgetter
from typing import List, Optional, Tuple


class ManualBreak:
    __slots__ = ('start_time', 'end_time', 'diff_allowed', 'duration',)

    def __init__(self, start_time, end_time, diff_allowed_seconds: int):
        self.start_time: int = start_time
        self.end_time: int = end_time
        self.diff_allowed: int = diff_allowed_seconds  # seconds
        self.duration: int = end_time - start_time


class BreakInPart:
    def __init__(self, start_time, end_time):
        self.start_time: int = start_time
        self.end_time: int = end_time


class Part:
    TRANSIT = 't'
    SERVICE = 's'

    def __init__(self, start: int, end: int, kind, point):
        self.start: int = start
        self.end: int = end
        self.kind = kind
        self.point = point
        self.breaks: List[BreakInPart] = []


class ManualBreakInDriverRoute:
    CAN_NOT_INSERT_BREAK = 'can_not_insert'

    def __init__(self, parts: List[Part], breaks: List[ManualBreak]):
        self.breaks = breaks
        self.breaks.sort(key=attrgetter('start_time', 'end_time'))
        self.parts = parts
        self.validators = []

    def get_parts_with_breaks(self) -> Optional[List[Part]]:
        parts = copy.deepcopy(self.parts)
        if not self._possible_route_is_valid(parts):
            return
        for break_setting in self.breaks:
            parts = self._insert_break_to_parts(break_setting, parts)
            if parts == self.CAN_NOT_INSERT_BREAK:
                return
        return parts

    def _insert_break_to_parts(self, break_setting: ManualBreak, parts: List[Part]):
        break_out_of_route_time_window = \
            break_setting.start_time - break_setting.diff_allowed > parts[-1].end \
            or break_setting.end_time + break_setting.diff_allowed < parts[0].start
        if break_out_of_route_time_window:
            return parts
        passed_parts: List[Part] = []
        for part in parts:
            possible_break_interval = self._find_time_for_break_in_transit(break_setting, part)
            if possible_break_interval is not None:
                possible_result = self._insert_possible_break(
                    passed_parts,
                    copy.deepcopy(parts),
                    possible_break_interval
                )
                if self._possible_route_is_valid(possible_result):
                    return possible_result
            passed_parts.append(part)
        return self.CAN_NOT_INSERT_BREAK

    @staticmethod
    def _find_time_for_break_in_transit(break_setting: ManualBreak, part: Part):
        if part.kind == Part.TRANSIT:
            if part.start <= break_setting.start_time <= part.end:
                return break_setting.start_time, break_setting.end_time
            if break_setting.start_time <= part.start <= break_setting.start_time + break_setting.diff_allowed:
                return part.start, part.start + break_setting.duration
            if break_setting.start_time >= part.end >= break_setting.start_time - break_setting.diff_allowed:
                return part.end, part.end + break_setting.duration
        elif part.kind == Part.SERVICE:
            if part.start <= break_setting.start_time <= part.end:
                if break_setting.start_time - break_setting.diff_allowed <= part.start:
                    return part.start, part.start + break_setting.duration
                elif break_setting.start_time + break_setting.diff_allowed > part.end:
                    return
                else:
                    return part.start, break_setting.end_time
        return

    @staticmethod
    def _insert_possible_break(passed_parts: List[Part], parts: List[Part],
                               possible_break_interval: Tuple[int, int]) -> Optional[List[Part]]:
        result = list(passed_parts)
        current = parts[len(result)]
        if current.kind == Part.TRANSIT:
            current.end = max(
                current.end + (possible_break_interval[1] - possible_break_interval[0]),
                possible_break_interval[1]
            )
            current.breaks.append(BreakInPart(*possible_break_interval))
        elif len(result) > 0:
            result[-1].end = max(
                result[-1].end + (possible_break_interval[1] - possible_break_interval[0]),
                possible_break_interval[1]
            )
            current.start, current.end = result[-1].end, result[-1].end + current.end - current.start
            result[-1].breaks.append(BreakInPart(*possible_break_interval))
        result.append(current)
        for other_part in parts[len(result):]:
            other_part.start, other_part.end = result[-1].end, result[-1].end + other_part.end - other_part.start
            result.append(other_part)
        return result

    def _possible_route_is_valid(self, parts: List[Part]):
        for validator in self.validators:
            if not validator(parts):
                return False
        return True
