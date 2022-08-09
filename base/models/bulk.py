from django.db import models

from rest_framework import serializers

from jsonfield import JSONField

from base.csv_parsing import BulkScheduleUploadResultSerializer, CSVValidateDriverSerializer, DriverCSVParser
from radaro_utils.radaro_csv.exceptions import CSVEncodingError, MissingRequiredHeadersException
from radaro_utils.radaro_csv.models import CSVFile
from radaro_utils.radaro_delayed_tasks.models import DelayedTaskBase

messages = {
    'start_processing': 'File processing started.',
    'critical': 'Sorry, server unable to process file. We are investigating this error.',
    'optional_skipped': 'Skipped optional columns. They are missing or have invalid names.',
    'unknown_columns': 'Unknown columns are ignored.',
    'required_fields': 'Some required columns are not found or have invalid names.',
    'validation_error': 'Validation error',
    'finished': 'File processing has been finished.',
}


class DriverScheduleUpload(DelayedTaskBase):
    ADMIN = 'admin'
    WEB = 'web'
    API = 'api'
    NO_INFO = 'no_info'
    EXTERNAL_API = 'external'

    _method = (
        (ADMIN, 'admin'),
        (WEB, 'WEB'),
        (API, 'API'),
        (EXTERNAL_API, 'External API'),
        (NO_INFO, 'No info')
    )

    creator = models.ForeignKey('base.Member', null=True, blank=True, on_delete=models.SET_NULL)
    method = models.CharField(choices=_method, default=NO_INFO, max_length=10)
    uploaded_from = models.CharField(max_length=512, blank=True)
    merchant = models.ForeignKey('merchant.Merchant', null=True, blank=True, on_delete=models.SET_NULL)
    processed_data = JSONField(blank=True, null=True)

    def _when_begin(self, *args, **kwargs):
        self.parser = DriverCSVParser(self.csv_file)

        if self.parser.mapper.optional_missing:
            message = messages['optional_skipped'] + ' Columns: ' + ', '.join(self.parser.mapper.optional_missing)
            self.event(message, self.WARNING)
        if self.parser.mapper.unknown_columns:
            message = messages['unknown_columns'] + ' Columns: ' + ', '.join(self.parser.mapper.unknown_columns)
            self.event(message, self.WARNING)

        self.initial_data = list(self.parser)
        for line in range(len(self.initial_data)):
            self.initial_data[line]['line'] = line

        validate_serializer = CSVValidateDriverSerializer(
            data=self.initial_data, many=True, context={'bulk': self, 'target_date': self.csv_file.target_date},
        )
        validate_serializer.is_valid(raise_exception=True)
        self.validated_data = validate_serializer.validated_data

    def _when_complete(self, *args, **kwargs):
        from base.models import Car
        from schedule.models import Schedule

        self.processed_data = BulkScheduleUploadResultSerializer(self.validated_data, many=True).data
        self.save()

        for detail in self.validated_data:
            if 'schedule' in detail:
                schedule, created = Schedule.objects.get_or_create(member=detail['driver'])
                schedule.schedule['one_time'][self.csv_file.target_date] = detail['schedule']
                schedule.save()

            if 'capacity' in detail:
                car, created = Car.objects.get_or_create(member=detail['driver'])
                car.one_time_capacities[self.csv_file.target_date] = detail['capacity']
                car.save()

    def _when_fail(self, *args, **kwargs):
        pass

    def prepare_file(self):
        try:
            self.begin()
        except MissingRequiredHeadersException as exc:
            self.event(
                messages['required_fields'] + ' Missing columns: ' + ', '.join(exc.fields),
                self.ERROR,
                prevent_save=True,
            )
            self.fail()
        except serializers.ValidationError as exc:
            self.event(
                messages['validation_error'],
                self.ERROR,
                additional_details={'details': exc.detail},
                prevent_save=True
            )
            self.fail()
        except Exception:
            self.event(messages['critical'], DriverScheduleUpload.ERROR, prevent_save=True)
            self.fail()
        else:
            self.complete()
            self.event(messages['finished'], DriverScheduleUpload.INFO, prevent_save=True)
        self.save()

    def __str__(self):
        return 'Driver schedule and capacity upload {0}'.format(self.id)


class CSVDriverSchedulesFile(CSVFile):
    bulk = models.OneToOneField(DriverScheduleUpload, related_name='csv_file', on_delete=models.CASCADE)
    target_date = models.DateField()

    def _on_create(self):
        self.bulk.event(messages['start_processing'], DriverScheduleUpload.INFO)

        try:
            super()._on_create()
        except CSVEncodingError as exc:
            self.bulk.fail()
            self.bulk.event(str(exc), DriverScheduleUpload.ERROR, prevent_save=True)
            self.bulk.save()
        except Exception:
            self.bulk.fail()
            self.bulk.event(messages['critical'], DriverScheduleUpload.ERROR, prevent_save=True)
            self.bulk.save()
        finally:
            self.original_file_name = self.file.name
