from __future__ import absolute_import, unicode_literals

import json

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.db import connection
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView

from radaro_utils.helpers import DateTimeEncoder
from tasks.models import Order


@method_decorator(staff_member_required, name='dispatch')
class RoutesComparisonView(TemplateView):
    template_name = 'order/routes.html'

    def dispatch(self, request, *args, **kwargs):
        order_id = kwargs.get('order_id')
        self.order = get_object_or_404(Order, order_id=order_id)
        return super(RoutesComparisonView, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(RoutesComparisonView, self).get_context_data(**kwargs)
        context.update({'real_path': json.dumps(self.order.real_path), 'filtered_path': json.dumps(self.order.path),
                        'key': settings.GOOGLE_MAPS_V3_APIKEY})
        return context


@method_decorator(staff_member_required, name='dispatch')
class GeofencesComparisonView(TemplateView):
    template_name = 'order/geofences.html'

    def dispatch(self, request, *args, **kwargs):
        self.order_id = kwargs.get('order_id')
        self.order = get_object_or_404(Order, order_id=self.order_id)
        return super(GeofencesComparisonView, self).dispatch(request, *args, **kwargs)

    def _get_geofence_info(self):
        query_raw = '''
            select * from 
                (select *, row_number() over (partition by field, new_value order by timestamp desc) as rank from 
                    (select events.id as event_id, field, new_value, happened_at, orders.id as order_pk, driver_id 
                      from reporting_event as events 
                      join delivery."public".django_content_type as content_type
                      on events.content_type_id = content_type.id
                      join (select driver_id, id from tasks_order where id=%(id)s) as orders 
                      on (events.object_id=orders.id and content_type.model='order' 
                        and events.field in ('geofence_entered', 'geofence_entered_on_backend'))
                    ) as t1 
                    join 
                    (select member_id, location, timestamp from driver_driverlocation) as locations 
                    on (t1.driver_id=locations.member_id and t1.happened_at>=locations.timestamp)
                ) 
            as result where rank = 1;
        '''

        with connection.cursor() as cursor:
            cursor.execute(query_raw, {'id': self.order.id})
            desc = cursor.description
            return [
                dict(zip([col[0] for col in desc], row))
                for row in cursor.fetchall()
            ]

    def get_context_data(self, **kwargs):
        context = super(GeofencesComparisonView, self).get_context_data(**kwargs)
        data = self._get_geofence_info()
        context.update({'key': settings.GOOGLE_MAPS_V3_APIKEY, 'events': json.dumps(data, cls=DateTimeEncoder),
                        'deliver_address': json.dumps(self.order.deliver_address.location)})
        return context
