from django.core.validators import FileExtensionValidator

from rest_framework import serializers

from base.api.legacy.serializers import DelayedTaskSerializer
from base.models import CSVDriverSchedulesFile, DriverScheduleUpload


class WebScheduleDriverUploadSerializer(serializers.Serializer):
    date = serializers.DateField()
    file = serializers.FileField(validators=[FileExtensionValidator(allowed_extensions=['csv'])])

    def validate_date(self, value):
        if value < self.context['request'].user.current_merchant.today:
            raise serializers.ValidationError('You cannot specify the past day')

        return value

    def create(self, validated_data):
        request = self.context['request']
        csv_file = validated_data['file']
        date = validated_data['date']

        bulk = DriverScheduleUpload.objects.create(
            creator=request.user,
            merchant=request.user.current_merchant,
            method=DriverScheduleUpload.WEB,
            uploaded_from=request.headers.get('user-agent', '')
        )
        CSVDriverSchedulesFile.objects.create(file=csv_file, target_date=date, bulk=bulk)
        bulk.prepare_file()
        return bulk


class WebScheduleDriverUploadResultSerializer(DelayedTaskSerializer):
    original_file_name = serializers.CharField(source='csv_file.original_file_name')
    method = serializers.CharField(source='get_method_display')
    processed_data = serializers.JSONField(allow_null=True)

    class Meta:
        model = DriverScheduleUpload
        fields = DelayedTaskSerializer.Meta.fields + ('method', 'original_file_name', 'processed_data')
