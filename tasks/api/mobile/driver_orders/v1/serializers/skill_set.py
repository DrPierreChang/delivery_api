from django.db.models import Count
from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers

from base.models import Member


class OrderSkillSetsValidator:
    order = None

    def set_context(self, serializer):
        self.order = getattr(serializer, 'instance', None)

    def __call__(self, attrs):
        if 'skill_sets' not in attrs and 'driver' not in attrs:
            return

        merchant = attrs.get('merchant', None) or self.order.merchant
        if not merchant.enable_skill_sets:
            return

        if self.order is not None:
            skill_sets = attrs.get('skill_sets', self.order.skill_sets.all())
            driver = attrs.get('driver', self.order.driver)
        else:
            skill_sets = attrs.get('skill_sets', None)
            driver = attrs.get('driver', None)

        if not skill_sets:
            return

        if driver:
            order_skill_set_ids = {skill.id for skill in skill_sets}
            driver_skill_set_ids = set(driver.skill_sets.values_list('id', flat=True))
            diff = order_skill_set_ids - driver_skill_set_ids
            if not diff:
                return
            raise serializers.ValidationError(
                {'driver_id': _("Driver {full_name} doesn't have all these skills".format(full_name=driver.full_name))},
                code='unskilled_driver'
            )
        else:
            available_drivers = Member.all_drivers.all().not_deleted().filter(skill_sets__in=skill_sets).values('id')
            available_drivers = available_drivers.annotate(count=Count('id')).filter(count=len(skill_sets)).exists()
            if available_drivers:
                return
            raise serializers.ValidationError(
                {'skill_set_ids': _('There are no drivers with the same set of skills.')},
                code='no_drivers_with_these_skills',
            )
