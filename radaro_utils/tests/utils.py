import os
import time

import psutil


class PerformanceMeasure(object):
    class PerformanceResult(object):
        _str_tmpl = 'Mem grabbed since last measure: {} MB\nTime passed since last measure: {} sec\n'

        time = None
        memory = None

        def __sub__(self, other):
            ret = type(self)()
            ret.time = self.time - other.time
            ret.memory = self.memory - other.memory
            return ret

        def render(self, tmpl):
            return tmpl.format(time=self.time, memory=self.time)

        def __str__(self):
            return self._str_tmpl.format(self.memory, self.time)

    measurement = None

    def __init__(self):
        self.process = psutil.Process(os.getpid())
        self.measurement = self.PerformanceResult()
        self.measurement.time = self.check_time()
        self.measurement.memory = self.mem_usage()

    def check_time(self):
        return time.time()

    def mem_usage(self):
        return self.process.memory_info()[0] / 2**20

    def measure(self):
        last_measurement = self.measurement
        self.measurement = self.PerformanceResult()
        self.measurement.time = self.check_time()
        self.measurement.memory = self.mem_usage()
        diff = self.measurement - last_measurement
        return self, diff

    def __str__(self):
        return 'Mem used: {} MB. Clock: {} sec\n'.format(self.measurement.memory, self.measurement.time)
