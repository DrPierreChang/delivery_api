from django.core.management.base import BaseCommand

from base.models import Invite, Member
from base.signals import create_routing_instance
from radaro_router.models import RadaroRouter


class Command(BaseCommand):
    help = "Migrate existing 'Invite' and 'Member' instances to Radaro Router app."

    def handle(self, *args, **options):
        for invite in Invite.objects.filter(radaro_router_manager__isnull=True):
            create_routing_instance(invite)

        for member in Member.objects.exclude(role=Member.NOT_DEFINED).filter(radaro_router_manager__isnull=True):
            create_routing_instance(member)

        number_created = RadaroRouter.objects.count()
        number_unsynced = RadaroRouter.objects.filter(synced=False).count()
        self.stdout.write('{} instances were created, {} were not synced.'.format(number_created, number_unsynced))
