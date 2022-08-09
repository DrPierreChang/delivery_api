from rest_framework import serializers

from radaro_utils.serializers.fields import DurationInSecondsField

from .manager import DriverStatisticsSerializer


class DriverWorkStatusTimeStatisticPerWeekForDriverSerializer(serializers.Serializer):
    total_break_time = DurationInSecondsField(source='time.on_break.duration')
    total_work_time = serializers.SerializerMethodField(read_only=True)

    def get_total_work_time(self, instance):
        return int((instance['time']['working']['duration'] + instance['time']['on_break']['duration']).total_seconds())


class DriverWorkStatusTimeStatisticPerDayForDriverSerializer(DriverWorkStatusTimeStatisticPerWeekForDriverSerializer):
    time_since_last_break = DurationInSecondsField(source='time.on_break.end_timestamp')


class DriverTimeStatisticsForDriverSerializers(serializers.Serializer):
    today = DriverWorkStatusTimeStatisticPerDayForDriverSerializer()
    past_seven_days = DriverWorkStatusTimeStatisticPerWeekForDriverSerializer()


class DriverStatisticsForDriverSerializer(DriverStatisticsSerializer):
    time_stats = DriverTimeStatisticsForDriverSerializers()
