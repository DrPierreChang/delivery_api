from django.db.models import Count
from django.utils.translation import ngettext
from django.utils.translation import ugettext_lazy as _

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.relations import PrimaryKeyRelatedField

from base.models import Member
from merchant.models import SkillSet
from radaro_utils.utils import Pluralizer
from reporting.api.legacy.serializers.delta import DeltaSerializer
from reporting.model_mapping import serializer_map
from tasks.api.legacy.serializers.mixins import ActiveOrdersChangesValidationMixin


class SkillSetDestroyValidationMixin(ActiveOrdersChangesValidationMixin):

    def _get_active_error_msg(self, jobs_ids, relations):
        jobs_msg = ngettext("%(count)d active job that has",
                            "%(count)d active jobs that have",
                            len(jobs_ids)) % {
            'count': len(jobs_ids)
        }
        msg = ngettext("Can't delete the skill because you have %(jobs_msg)s this skill",
                       "Can't delete the skills because you have %(jobs_msg)s these skills",
                       len(relations)) % {
            'jobs_msg': jobs_msg
        }
        return msg

    def _get_assigned_error_msg(self, jobs_ids, relations):
        request = self.context.get('request')
        unassigned_from = _('you') if request.user.is_driver else ngettext("driver", "drivers", len(jobs_ids))
        jobs_msg = ngettext("%(count)d job that has",
                            "%(count)d jobs that have",
                            len(jobs_ids)) % {'count': len(jobs_ids)}
        msg = ngettext("%(jobs_msg)s this skill will be unassigned from %(from)s after you delete the skill",
                       "%(jobs_msg)s these skills will be unassigned from %(from)s after you delete the skills",
                       len(relations)) % {
            'jobs_msg': jobs_msg,
            'from': unassigned_from
        }
        return msg


class OrderSkillSetsValidationMixin(object):

    def _validate_skill_sets_for_driver(self, skill_sets, driver):
        if not skill_sets:
            return
        if not driver:
            available_drivers = Member.objects.filter(skill_sets__in=skill_sets).values('id')\
                .annotate(count=Count('id')).filter(count=len(skill_sets)).exists()
            if available_drivers:
                return
            raise ValidationError(
                {"skill_sets": "There are no drivers with the same set of skills."}
            )
        diff = set(skill.id for skill in skill_sets).difference(
            set(driver.skill_sets.values_list('id', flat=True))
        )
        if not diff:
            return
        error_msg = "Driver {0} doesn't have all these skills"
        raise ValidationError(error_msg.format(driver.full_name))


@serializer_map.register_serializer_for_detailed_dump(version='web')
@serializer_map.register_serializer_for_detailed_dump(version=2)
@serializer_map.register_serializer_for_detailed_dump(version=1)
class SkillSetSerializer(serializers.ModelSerializer):
    drivers_count = serializers.SerializerMethodField()

    class Meta:
        model = SkillSet
        fields = '__all__'
        read_only_fields = ('merchant', )

    def validate(self, attrs):
        name = attrs.get('name', self.instance.name if self.instance else None)
        color = attrs.get('color', self.instance.color if self.instance else '')
        merchant = self.context['request'].user.current_merchant

        qs = SkillSet.objects.filter(name=name, color=color, merchant=merchant)
        if self.instance:
            qs = qs.exclude(id=self.instance.id)

        if qs.exists():
            raise ValidationError("The fields name, color must make a unique set.")

        return attrs

    def get_drivers_count(self, instance):
        return instance.drivers.count()


@serializer_map.register_serializer
class SkillSetDeltaSerializer(DeltaSerializer):
    class Meta(DeltaSerializer.Meta):
        model = SkillSet


class RelatedSkillSetSerializer(SkillSetDestroyValidationMixin, serializers.Serializer):
    skill_sets = serializers.ManyRelatedField(
        required=False,
        child_relation=PrimaryKeyRelatedField(
            queryset=SkillSet.objects.filter(is_secret=False),
            required=False
        )
    )

    def validate_skill_sets(self, attrs):
        request = self.context.get('request')
        merchant = request.user.current_merchant
        not_merchant_objs = [attr for attr in attrs if attr.merchant != merchant]

        if not_merchant_objs:
            raise ValidationError("This is not merchant's skill sets")

        return attrs

    def validate(self, attrs):
        request = self.context.get('request')
        skill_sets = attrs.get('skill_sets', [])

        if request.method == 'DELETE':
            self._validate_on_destroy(
                skill_sets,
                request.user.order_set.all().annotate_job_type_for_skillsets(skill_sets),
                background_notification=True
            )
        return attrs


class ExternalSkillSetSerializer(SkillSetSerializer):
    driver_ids = serializers.PrimaryKeyRelatedField(many=True, read_only=True, source='drivers')
    member_ids = serializers.SlugRelatedField(many=True, read_only=True, slug_field='member_id', source='drivers')

    class Meta:
        model = SkillSet
        fields = '__all__'


__all__ = ['ExternalSkillSetSerializer', 'RelatedSkillSetSerializer',
           'SkillSetDeltaSerializer', 'SkillSetSerializer']
