from django.core.management import BaseCommand

from base.models import Invite, Member


class Command(BaseCommand):
    help = 'Activates remote router instances for specified merchant'

    def add_arguments(self, parser):
        parser.add_argument('merchant_id', type=int)

    def handle(self, *args, **options):
        merchant_id = options.get('merchant_id')

        members = Member.objects.filter(merchant_id=merchant_id)
        member_ids = members.values_list('id')
        invites = Invite.objects.filter(initiator_id__in=member_ids)

        instances = list(filter(lambda obj: obj.radaro_router.remote_id is not None, list(members) + list(invites)))
        for instance in instances:
            instance.radaro_router.activate_remote_instance()

        self.stdout.write('Activated {} router instances'.format(len(instances)))
