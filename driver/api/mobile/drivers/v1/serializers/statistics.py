from django.contrib.auth import get_user_model
from django.db.models import Count

from rest_framework import serializers

from base.utils import get_driver_statistics
from radaro_utils.serializers.fields import DurationInSecondsField
from tasks.mixins.order_status import OrderStatus


class WeekWorkStatusDriverStatisticSerializer(serializers.Serializer):
    total_break_time = DurationInSecondsField(source='time.on_break.duration')
    total_work_time = serializers.SerializerMethodField(read_only=True)

    def get_total_work_time(self, instance):
        return int((instance['time']['working']['duration'] + instance['time']['on_break']['duration']).total_seconds())


class TodayWorkStatusDriverStatisticSerializer(WeekWorkStatusDriverStatisticSerializer):
    time_since_last_break = DurationInSecondsField(source='time.on_break.end_timestamp')


class WorkStatusDriverStatisticSerializer(serializers.Serializer):
    today = TodayWorkStatusDriverStatisticSerializer()
    past_seven_days = WeekWorkStatusDriverStatisticSerializer()

    def to_representation(self, instance):
        return super().to_representation(get_driver_statistics(instance))


class DriverStatisticSerializer(serializers.ModelSerializer):
    skill_set_count = serializers.SerializerMethodField()
    order_stats = serializers.SerializerMethodField()
    work_status_stats = WorkStatusDriverStatisticSerializer(source='*')

    class Meta:
        model = get_user_model()
        fields = ('id', 'order_stats', 'skill_set_count', 'work_status_stats')

    def get_skill_set_count(self, instance):
        return instance.skill_sets.count()

    def get_order_stats(self, instance):
        statuses = [OrderStatus.DELIVERED, OrderStatus.FAILED]

        orders = instance.orders.filter(deleted=False, status__in=statuses)
        order_status_stats = orders.values('status').annotate(count_orders=Count('id'))

        result = {status: 0 for status in statuses}
        for item in order_status_stats:
            result[item['status']] = item['count_orders']

        return result
