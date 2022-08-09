from django.urls import include, path

from rest_framework.routers import DefaultRouter

from .schedule.v1.views import ScheduleViewSet
from .schedule_calendar.v1.views import MobileCalendarScheduleViewSet

router = DefaultRouter()
router.register('schedules/v1', ScheduleViewSet)
router.register('schedules_calendar/v1', MobileCalendarScheduleViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
