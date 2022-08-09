from django.core.management import BaseCommand

from base.models import Invite, Member
from driver.utils import WorkStatus


class Command(BaseCommand):
    help = 'Deactivates remote router instances for specified merchant'

    def add_arguments(self, parser):
        parser.add_argument('merchant_id', type=int)

    def handle(self, *args, **options):
        merchant_id = options.get('merchant_id')

        members = Member.objects.filter(merchant_id=merchant_id)
        member_ids = members.values_list('id')
        invites = Invite.objects.filter(initiator_id__in=member_ids)

        instances = list(filter(lambda obj: obj.radaro_router.remote_id is not None, list(members) + list(invites)))

        for member in members:
            member.user_auth_tokens.all().delete()
            if member.is_driver:
                member.work_status = WorkStatus.NOT_WORKING
                member.save()

        self.stdout.write('Logged out {} members'.format(members.count()))

        for instance in instances:
            instance.radaro_router.deactivate_remote_instance()

        self.stdout.write('Deactivated {} router instances'.format(len(instances)))
