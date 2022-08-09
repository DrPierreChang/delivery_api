from datetime import timedelta

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone

from base.models import Member
from schedule.fields import ScheduleField


class Schedule(models.Model):
    member = models.OneToOneField(Member, null=False, blank=False, related_name='schedule', on_delete=models.CASCADE)
    schedule = ScheduleField(encoder=DjangoJSONEncoder)

    class Meta:
        verbose_name = 'schedule'
        verbose_name_plural = 'schedules'

    def __str__(self):
        return 'Schedule id: {0}'.format(self.id)

    @property
    def today(self):
        tz = self.member.current_merchant.timezone
        return timezone.now().astimezone(tz).date()

    def convert_weekday_to_date(self, weekday):
        today = self.today

        # Calculating how many days the day of the week will come.
        delta = weekday - today.weekday()
        if delta <= 0:
            delta += 7

        day = today + timedelta(days=delta)
        return day

    def week_schedule(self):
        weeks_schedule = {
            weekday: {'one_time': False, 'breaks': [], **daily_schedule}
            for weekday, daily_schedule in self.schedule['constant'].items()
        }

        today = self.today
        one_week_later = today + timedelta(days=7)

        for day, daily_schedule in self.schedule['one_time'].items():
            if daily_schedule and today <= day < one_week_later:
                weeks_schedule[day.weekday()].update(**daily_schedule, one_time=True)

        return weeks_schedule

    def update_schedule(self, data):
        weekdays_with_new_schedule = list(data['constant'].keys())
        today = self.today
        for day in list(self.schedule['one_time'].keys()):
            # Deletion of one_time items corresponding to the new items in constant
            if day.weekday() in weekdays_with_new_schedule:
                del self.schedule['one_time'][day]

            # Deletion of expired items.
            elif day < today:
                del self.schedule['one_time'][day]

        for day in data['constant'].keys():
            if day in self.schedule['constant']:
                self.schedule['constant'][day].update(data['constant'][day])
            else:
                self.schedule['constant'][day] = data['constant'][day]

        for day in data['one_time'].keys():
            if data['one_time'][day]:
                if day in self.schedule['one_time']:
                    self.schedule['one_time'][day].update(data['one_time'][day])
                else:
                    self.schedule['one_time'][day] = data['one_time'][day]

                sh = self.schedule['one_time'][day]
                if not sh.get('breaks', []):
                    sh.pop('breaks', [])
                if sh == {} or sh == {'day_off': False}:
                    self.schedule['one_time'].pop(day, {})

        self.save()
        return self

    def get_day_schedule(self, day):
        return {
            **self.schedule['constant'][day.weekday()],
            **self.schedule['one_time'].get(day, {}),
        }
