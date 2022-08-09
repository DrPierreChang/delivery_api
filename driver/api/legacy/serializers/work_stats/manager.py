from rest_framework import serializers

from radaro_utils.serializers.fields import DurationInSecondsField


class DriverWorkStatusTimeStatisticPerWeekSerializer(serializers.Serializer):
    breaks_count = serializers.IntegerField(source='time.on_break.count')
    total_break_time = DurationInSecondsField(source='time.on_break.duration')
    work_time = DurationInSecondsField(source='time.working.duration')
    total_work_time = serializers.SerializerMethodField(read_only=True)

    def get_total_work_time(self, instance):
        return int((instance['time']['working']['duration'] + instance['time']['on_break']['duration']).total_seconds())


class DriverTimeStatisticsSerializer(serializers.Serializer):
    today = DriverWorkStatusTimeStatisticPerWeekSerializer()
    past_seven_days = DriverWorkStatusTimeStatisticPerWeekSerializer()


class DriverStatisticsSerializer(serializers.Serializer):
    date_joined = serializers.DateTimeField()
    last_online_change = serializers.DateTimeField()
    completed_jobs = serializers.IntegerField()
    low_rating_jobs = serializers.IntegerField()
    average_rating = serializers.FloatField()
    time_stats = DriverTimeStatisticsSerializer()
