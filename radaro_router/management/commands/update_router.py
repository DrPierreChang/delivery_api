from django.core.management import BaseCommand

from base.models import Invite, Member
from base.signals import get_serializer_class
from radaro_router.celery_tasks import update_radaro_router_instance


class Command(BaseCommand):
    help = 'Updates remote router instances with the newest info for specified merchant. Especially helpful for ' \
           'host info updates which are not applied automatically.'

    def add_arguments(self, parser):
        parser.add_argument('merchant_id', type=int)

    def handle(self, *args, **options):
        merchant_id = options.get('merchant_id')

        members = Member.objects.filter(merchant_id=merchant_id)
        member_ids = members.values_list('id')
        invites = Invite.objects.filter(initiator_id__in=member_ids)

        instances = list(members) + list(invites)

        for instance in instances:
            serializer_class = get_serializer_class(type(instance).__name__)
            serializer = serializer_class(instance)
            extra = serializer.data

            if not instance.radaro_router.remote_id:
                instance.update_radaro_router(extra=extra)
                continue
            update_radaro_router_instance(instance.radaro_router.id, serializer.data)

        self.stdout.write('Successfully updated {} router instances'.format(len(instances)))
