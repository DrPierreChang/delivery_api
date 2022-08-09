from rest_framework import serializers

from base.api.legacy.serializers.members import ManagerSerializer
from merchant.models import Merchant


class GroupMerchantSerializer(serializers.ModelSerializer):
    subbrandings = serializers.SerializerMethodField()

    class Meta:
        model = Merchant
        fields = ('id', 'name', 'subbrandings')

    def get_subbrandings(self, merchant):
        from tasks.api.legacy.serializers.core import SubBrandingTableSerializer

        sub_brand_qs = merchant.subbrandings\
            .filter(id__in=self.context['request'].user.sub_brandings.all().values_list('id', flat=True))
        data = SubBrandingTableSerializer(sub_brand_qs, many=True).data
        return data


class GroupManagerSerializer(ManagerSerializer):
    merchants = GroupMerchantSerializer(many=True, read_only=True)
    enable_labels = serializers.SerializerMethodField()
    use_pick_up_status = serializers.SerializerMethodField()
    use_way_back_status = serializers.SerializerMethodField()

    class Meta(ManagerSerializer.Meta):
        fields = ManagerSerializer.Meta.fields + ('merchants', 'show_only_sub_branding_jobs')

    def get_enable_labels(self, group_manager):
        return any(group_manager.merchants.all().values_list('enable_labels', flat=True))

    def get_use_pick_up_status(self, group_manager):
        return any(group_manager.merchants.all().values_list('use_pick_up_status', flat=True))

    def get_use_way_back_status(self, group_manager):
        return any(group_manager.merchants.all().values_list('use_way_back_status', flat=True))
