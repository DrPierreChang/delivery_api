from django.urls import include, path

from rest_framework.routers import DefaultRouter

from .schedule.views import ScheduleCalendarViewSet, ScheduleViewSet

router = DefaultRouter()
router.register('schedules', ScheduleViewSet)
router.register('schedules_calendar', ScheduleCalendarViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
