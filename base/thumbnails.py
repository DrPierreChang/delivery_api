from django.db.models import Q

from base.models import Member
from merchant.models import Merchant
from radaro_utils import helpers


def create_thumbnails():
    for Cl, im_name in ((Member, 'avatar'), (Merchant, 'logo')):
        th_name = 'thumb_{}_100x100_field'.format(im_name)
        filter_by = {
            im_name + '__isnull': False,
            th_name + '__isnull': True,
        }
        filter_query = Q(**{im_name + '__isnull': False}) & \
                       (Q(**{th_name + '__isnull': True}) | Q(**{th_name: ''}))
        exclude_query = Q(**{im_name: ''})
        q = Cl.all_objects.filter(filter_query).exclude(exclude_query)
        for q_chunk in helpers.chunks(q, length=q.count(), n=500):
            for m in q_chunk:
                m.thumbnailer.generate_for(im_name)
