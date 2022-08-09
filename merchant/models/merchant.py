from __future__ import absolute_import, unicode_literals

import datetime
import os
import re

from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.postgres.fields import ArrayField, CIEmailField, JSONField
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Case, F, IntegerField, Q, When
from django.utils.functional import cached_property
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import ugettext_lazy as _

from constance import config
from location_field.models.plain import PlainLocationField
from model_utils import Choices, FieldTracker
from timezone_field import TimeZoneField

from base.utils import get_upload_path_100x100
from merchant.constants import EditableManagerDefaultsMixin as DefaultsMixin
from merchant.fields.screen_text_field import SCREEN_TEXT_FIELDS
from merchant.models.mixins import MerchantTypes
from merchant.utils import ReportsFrequencySettingsMixin, count_subquery, get_used_countries_from_set
from notification.mixins import MessageTemplateStatus
from notification.models import Device, MerchantMessageTemplate, PushNotificationsSettings, SendNotificationMixin
from radaro_utils import countries as radaro_countries
from radaro_utils.files.utils import get_upload_path
from radaro_utils.models import ResizeImageMixin
from radaro_utils.radaro_model_utils.mixins import TrackMixin
from radaro_utils.radaro_phone.models import PhoneField
from radaro_utils.radaro_phone.utils import e164_phone_format, phone_is_valid
from radaro_utils.sftp_client import SFTPMerchantClient
from route_optimisation.const import MerchantOptimisationFocus, MerchantOptimisationTypes

from ..image_specs import ThumbnailGenerator
from .fields import MerchantHasRelatedSurveys, SmsSenderField


def generate_webhook_verification_token():
    return urlsafe_base64_encode(os.urandom(16))


def get_api_server_url():
    return "https://{}".format(settings.CURRENT_HOST)


def get_review_screen_default_text():
    return '<p class=\"ratingModal__taskHeaderText\">Well, we\'re all done!</p>\n' \
           '<p class=\"ratingModal__rateText\">Please, rate our service.</p>'


def default_merchant_countries():
    return [radaro_countries.AUSTRALIA, ]


def default_job_failure_screen_text_dict():
    val = {field: '' for field, _ in SCREEN_TEXT_FIELDS}
    val['heading'] = 'The delivery has been unsuccessful this time'
    val['second_heading'] = ''
    val['sub_heading'] = 'Please contact us for more information'
    return val


def default_assigned_job_screen_text_dict():
    val = {field: '' for field, _ in SCREEN_TEXT_FIELDS}
    val['heading'] = 'Your order is out for delivery'
    val['second_heading'] = 'You are number {{ queue }} in queue'
    val['sub_heading'] = 'Expect delivery between {{ delivery_interval }}'
    return val


def default_not_assigned_job_screen_text_dict():
    val = {field: '' for field, _ in SCREEN_TEXT_FIELDS}
    val['heading'] = 'You have an upcoming order from {{ merchant }} on {{ delivery_day_short }} ' \
                     'between {{ delivery_interval }}'
    val['second_heading'] = ''
    val['sub_heading'] = 'Stay tuned!'
    return val


class MerchantManager(models.Manager):

    def cms_report_data(self, date_from, date_to, merchant_id=None):
        params = {'date_from': date_from, 'date_to': date_to, 'tz': settings.TIME_ZONE}
        if merchant_id:
            merchant_filter = 'WHERE m.id = %(merchant_id)s'
            params['merchant_id'] = merchant_id
        else:
            merchant_filter = ''

        if not (date_to and date_from):
            date_filter = ''
        else:
            date_filter = 'WHERE ({field} at time zone %(tz)s)::date between date %(date_from)s and date %(date_to)s'

        sms_sub = """
            SELECT msg_template.merchant_id,
            SUM(CASE WHEN (msg_template.template_type=1) THEN sms_msg.segment_count ELSE 0 END ) AS sms_order_in_progress,
            SUM(CASE WHEN (msg_template.template_type=2) THEN sms_msg.segment_count ELSE 0 END ) AS sms_order_terminated,
            SUM(CASE WHEN (msg_template.template_type=3) THEN sms_msg.segment_count ELSE 0 END ) AS sms_order_follow_up,
            SUM(CASE WHEN (msg_template.template_type=4) THEN sms_msg.segment_count ELSE 0 END ) AS sms_order_follow_up_reminder,
            SUM(CASE WHEN (msg_template.template_type=6) THEN sms_msg.segment_count ELSE 0 END ) AS sms_invitation,
            SUM(CASE WHEN (msg_template.template_type=7) THEN sms_msg.segment_count ELSE 0 END ) AS sms_invitation_complete,
            SUM(CASE WHEN (msg_template.template_type=13) THEN sms_msg.segment_count ELSE 0 END ) AS sms_order_upcoming_delivery,
            SUM(CASE WHEN (msg_template.template_type in (1, 2, 3, 4, 13)) THEN sms_msg.segment_count ELSE 0 END ) AS total_customer_sms,
            SUM(CASE WHEN (msg_template.template_type in (6, 7)) THEN sms_msg.segment_count ELSE 0 END ) AS total_driver_sms
            FROM notification_merchantmessagetemplate AS msg_template
            JOIN notification_templatesmsmessage sms_msg on msg_template.id = sms_msg.template_id {filter}
            GROUP BY msg_template.merchant_id
        """.format(filter=date_filter.format(field='sms_msg.sent_at'))

        jobs_sub = """SELECT merchant_id, COUNT(id) as amount FROM tasks_order {filter}
                      GROUP BY merchant_id""".format(filter=date_filter.format(field='created_at'))

        return self.raw("""
            SELECT m.id, m.name, COALESCE(j.amount, 0) as jobs,
            COALESCE(s1.sms_order_in_progress, 0) as sms_order_in_progress,
            COALESCE(s1.sms_order_terminated, 0) as sms_order_terminated,
            COALESCE(s1.sms_order_follow_up, 0) as sms_order_follow_up,
            COALESCE(s1.sms_order_follow_up_reminder, 0) as sms_order_follow_up_reminder,
            COALESCE(s1.sms_order_upcoming_delivery, 0) as sms_order_upcoming_delivery,
            COALESCE(s1.sms_invitation, 0) as sms_invitation,
            COALESCE(s1.sms_invitation_complete, 0) as sms_invitation_complete,
            COALESCE(s1.total_customer_sms, 0) as total_customer_sms,
            COALESCE(s1.total_driver_sms, 0) as total_driver_sms
            FROM merchant_merchant m
            LEFT JOIN ({sms_sub}) as s1 on s1.merchant_id = m.id
            LEFT JOIN ({jobs_sub}) as j on j.merchant_id = m.id
            {merchant_filter}
            ORDER BY m.name;
            """.format(sms_sub=sms_sub,
                       jobs_sub=jobs_sub,
                       merchant_filter=merchant_filter
                       ), params
        )

    def jobs_usage_report(self, current_period, previous_period):
        from tasks.models.orders import Order
        filter_field = 'created_at'

        percent_calculation = (F('count') - F('previous_count')) * 100 / F('previous_count')
        return self.get_queryset().annotate(
            count=count_subquery(Order, filter_field, current_period),
            previous_count=count_subquery(Order, filter_field, previous_period),
            percent_growth=Case(
                When(previous_count__gt=0, then=percent_calculation),
                default=None,
                output_field=IntegerField())
        ).order_by(F('count').desc(nulls_last=True), F('percent_growth').desc(nulls_last=True)).\
            values('name', 'percent_growth', 'count', 'previous_count')

    def drivers_usage_report(self, current_period):
        from base.models.members import Member

        return self.get_queryset().annotate(
            count=count_subquery(Member, 'last_ping', current_period, extra_filter=Q(role=1)),
        ).order_by(F('count').desc(nulls_last=True)).values('name', 'count')


class Merchant(SendNotificationMixin,
               ResizeImageMixin,
               TrackMixin,
               DefaultsMixin,
               ReportsFrequencySettingsMixin,
               models.Model):
    DISABLED = 0
    UPON_ENTERING = 1
    UPON_EXITING = 2

    geofences = (
        (DISABLED, 'Complete ONLY on Driver Input'),
        (UPON_ENTERING, 'Complete upon ENTER or Driver Input'),
        (UPON_EXITING, 'Complete upon EXIT or Driver Input'),
    )

    NO_ANIMATION = 0
    ANIMATION = 1
    ANIMATION_WITH_SNAP_TO_ROADS = 2
    PATH_PROCESSING_CHOICES = (
        (NO_ANIMATION, 'Driver movement without animation'),
        (ANIMATION, 'Driver movement with animation'),
        (ANIMATION_WITH_SNAP_TO_ROADS, 'Driver movement animation with snapping to roads'),
    )

    EMPTY_PHONE = ''
    DRIVER_PHONE = 'driver'
    MERCHANT_PHONE = 'merchant'
    SUBBRAND_PHONE = 'sub_branding'

    phone_choices = (
        (EMPTY_PHONE, 'Not display the phone number'),
        (DRIVER_PHONE, 'Driver phone number'),
        (MERCHANT_PHONE, 'Merchant phone number'),
        (SUBBRAND_PHONE, 'Sub-brand phone number')
    )

    ROUTE_OPTIMIZATION_DISABLED = 'disabled'

    route_optimization_choices = (
        (ROUTE_OPTIMIZATION_DISABLED, 'Disabled'),
        (MerchantOptimisationTypes.PTV, 'PTV'),
        (MerchantOptimisationTypes.OR_TOOLS, 'Google\'s OR Tools'),
        (MerchantOptimisationTypes.PTV_SMARTOUR_EXPORT, 'PTV Smartour export'),
    )

    route_optimization_focus_choices = (
        (MerchantOptimisationFocus.MINIMAL_TIME, 'Minimal route time (drivers might be skipped)'),
        (MerchantOptimisationFocus.TIME_BALANCE, 'Balanced by route time (route assignment among all drivers)'),
        (MerchantOptimisationFocus.ALL, 'Combined optimisation (based on minimal & balanced by route time)'),
        (MerchantOptimisationFocus.OLD, 'Old algorithm version'),
    )

    job_service_time_choices = (
        (3, '3 Minutes'),
        (5, '5 Minutes'),
        (10, '10 Minutes'),
        (15, '15 Minutes'),
        (20, '20 Minutes'),
        (30, '30 Minutes'),
        (45, '45 Minutes'),
        (60, '1 Hour'),
        (90, '90 Minutes'),
        (120, '2 Hours'),
    )

    TYPES_BARCODES = Choices(
        ('disable', 'Disable'),
        ('before', 'Scan at the warehouse'),
        ('after', 'Scan upon delivery'),
        ('both', 'Scan both times'),
    )

    INSTANT_UPCOMIG_DELIVERY = 'instant'
    DAY_BEFORE_UPCOMIG_DELIVERY = 'day_before'
    MIXED_UPCOMIG_DELIVERY = 'mixed'


    _upcoming_delivery_choices = (
        (INSTANT_UPCOMIG_DELIVERY, 'Instant'),
        (DAY_BEFORE_UPCOMIG_DELIVERY, '24h before deadline'),
        (MIXED_UPCOMIG_DELIVERY, 'Instant and 24h before deadline')

    )

    ADVANCED_COMPLETION_DISABLED = 'disabled'
    ADVANCED_COMPLETION_OPTIONAL = 'optional'
    ADVANCED_COMPLETION_REQUIRED = 'required'

    advanced_completion_choices = (
        (ADVANCED_COMPLETION_DISABLED, 'Disabled'),
        (ADVANCED_COMPLETION_OPTIONAL, 'Optional'),
        (ADVANCED_COMPLETION_REQUIRED, 'Required')
    )

    SCANNED_DOCUMENT_OUTPUT_SIZE_DEFAULT = 'default'
    SCANNED_DOCUMENT_OUTPUT_SIZE_A4 = 'a4'
    SCANNED_DOCUMENT_OUTPUT_SIZE_US_LETTER = 'us letter'

    scanned_document_output_size_choices = (
        (SCANNED_DOCUMENT_OUTPUT_SIZE_DEFAULT, 'Default'),
        (SCANNED_DOCUMENT_OUTPUT_SIZE_A4, 'A4'),
        (SCANNED_DOCUMENT_OUTPUT_SIZE_US_LETTER, 'US Letter'),
    )

    MAX_ABN = 99999999999

    tracker = FieldTracker()
    track_fields = {'logo'}

    untracked_for_events = ()

    thumbnailer = ThumbnailGenerator({'logo': 'thumb_logo_100x100_field'})

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    address = models.CharField(max_length=255, null=True, blank=True)
    location = PlainLocationField(based_fields=['address'], zoom=7, blank=True, null=True, default=None)
    logo = models.ImageField(null=True, blank=True, upload_to=get_upload_path)
    thumb_logo_100x100_field = models.ImageField(null=True, blank=True, editable=False,
                                                 upload_to=get_upload_path_100x100)
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=50)
    created_at = models.DateTimeField(auto_now_add=True)
    merchant_identifier = models.CharField(max_length=50, null=True, blank=True)
    api_multi_key = models.ForeignKey('webhooks.MerchantAPIKey', blank=True, null=True, on_delete=models.SET_NULL,
                                      related_name='merchants')

    enable_delivery_confirmation = models.BooleanField(default=False)
    enable_delivery_pre_confirmation = models.BooleanField(default=False,
                                                           help_text='This setting enables delivery pre-inspection: '
                                                                     'pre-inspection photos, pre-inspection signature,'
                                                                     'pre-inspection comment ',
                                                           verbose_name='Enable delivery pre-inspection')
    enable_pick_up_confirmation = models.BooleanField(default=False)
    enable_delivery_confirmation_documents = models.BooleanField(
        default=False,
        help_text='To activate this option, require an enable delivery confirmation',
    )
    enable_reminder_to_attach_confirmation_documents = models.BooleanField(default=False)
    scanned_document_output_size = models.CharField(
        choices=scanned_document_output_size_choices,
        default=SCANNED_DOCUMENT_OUTPUT_SIZE_DEFAULT,
        max_length=20,
    )

    geofence_settings = models.IntegerField(choices=geofences, default=DISABLED)

    phone = PhoneField(blank=True)

    # According to Australian government pages 11 digit unique number
    abn = models.CharField(max_length=255, blank=True, null=True)

    distance_show_in = models.FloatField(choices=DefaultsMixin.distances, default=DefaultsMixin.KM)
    is_blocked = models.BooleanField(default=False)
    store_url = models.URLField(default='http://www.example.com/', verbose_name='Custom “URL” redirect link')
    feedback_redirect_enabled = models.BooleanField(
        default=False,
        help_text='Redirect to custom URL without Radaro review',
    )

    countries = ArrayField(
        models.CharField(choices=radaro_countries.countries, default=radaro_countries.AUSTRALIA, max_length=20),
        default=default_merchant_countries
    )
    timezone = TimeZoneField(default=settings.TIME_ZONE)
    date_format = models.CharField(default=DefaultsMixin.LITTLE_ENDIAN, choices=DefaultsMixin.date_formats,
                                   max_length=64,
                                   help_text='This setting also affects processing incoming data. So there could be '
                                             'mistakes in processing dates of CSV file if user will suppose a date '
                                             'format, different from the one set here.')
    language = models.CharField(
        max_length=10, choices=settings.LANGUAGES, default=settings.USER_DEFAULT_LANGUAGE_CODE,
        help_text='Language used for customer tracking and as a preferred language while searching job addresses'
    )
    coloured_map = models.BooleanField(default=True)
    use_subbranding = models.BooleanField(default=False)
    shorten_sms_url = models.BooleanField(default=False)
    shorten_report_url = models.BooleanField(default=False)
    sms_enable = models.BooleanField(default=True)
    sms_sender = SmsSenderField(max_length=15, default='')
    sms_price = models.FloatField(validators=[MinValueValidator(0)], null=True, blank=True)
    job_price = models.FloatField(validators=[MinValueValidator(0)], null=True, blank=True)
    location_processing_price = models.FloatField(validators=[MinValueValidator(0)], null=True, blank=True)
    webhook_url = ArrayField(models.CharField(null=True, blank=True, max_length=500), default=list, blank=True, size=5)
    webhook_verification_token = models.CharField(max_length=255, default=generate_webhook_verification_token)
    webhook_failed_times = models.PositiveIntegerField(default=0)
    api_server_url = models.URLField(default=get_api_server_url)
    enable_job_description = models.BooleanField(default=False,
                                                 verbose_name='Rich text job descriptions enabled',
                                                 help_text='This setting enables additional markdown '
                                                           'descriptions for jobs.')
    enable_labels = models.BooleanField(default=False, verbose_name='Enable jobs labels')
    enable_skill_sets = models.BooleanField(default=False, verbose_name='Enable skill sets')

    path_processing = models.PositiveSmallIntegerField(
        choices=PATH_PROCESSING_CHOICES, default=NO_ANIMATION,
        help_text="This setting specifies the strategy for processing new driver's coordinates and drawing "
                  "car's movement on the map."
    )

    events = GenericRelation('reporting.Event', related_query_name='merchants')
    checklist = models.ForeignKey('merchant_extension.Checklist', null=True, blank=True, on_delete=models.SET_NULL)

    sod_checklist = models.ForeignKey('merchant_extension.Checklist', null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name='sod_merchants', verbose_name='Start-of-Day Checklist')
    sod_checklist_email = CIEmailField(max_length=50, blank=True, verbose_name='Start-of-Day Checklist Email',
                                       help_text='Use only with selected "sod_checklist" setting.')
    eod_checklist = models.ForeignKey('merchant_extension.Checklist', null=True, blank=True, on_delete=models.SET_NULL,
                                      related_name='eod_merchants', verbose_name='End-of-Day Checklist')
    eod_checklist_email = CIEmailField(max_length=50, blank=True, verbose_name='End-of-Day Checklist Email',
                                       help_text='Use only with selected "eod_checklist" setting.')
    customer_survey = models.ForeignKey('merchant_extension.Survey', null=True, blank=True, on_delete=models.SET_NULL,
                                        verbose_name='Customer Survey', related_name='merchants')
    has_related_surveys = MerchantHasRelatedSurveys()
    survey_export_email = CIEmailField(max_length=50, blank=True, help_text='Email to send survey export')
    customer_review_opt_in_enabled = models.BooleanField(
        verbose_name='Enable customer review opt-in', default=False
    )
    customer_review_opt_in_text = models.TextField(
        verbose_name='Customer review opt-in text',
        default='Tap here to allow us to publicly share your feedback.'
    )

    merchant_group = models.ForeignKey('MerchantGroup', null=True, blank=True, on_delete=models.SET_NULL, related_name='merchants')

    push_notifications_settings = models.ForeignKey(PushNotificationsSettings, on_delete=models.SET_NULL,
                                                    null=True, blank=True)

    use_pick_up_status = models.BooleanField(default=False)
    use_way_back_status = models.BooleanField(default=False, help_text='Available only with "use_hubs" setting.')
    use_hubs = models.BooleanField(default=False)
    customer_tracking_phone_settings = models.CharField(
        choices=phone_choices, max_length=100,
        default=EMPTY_PHONE, blank=True
    )
    show_company_name_for_customer = models.BooleanField(default=False)
    advanced_completion = models.CharField(max_length=50, choices=advanced_completion_choices,
                                           default=ADVANCED_COMPLETION_DISABLED)

    route_optimization = models.CharField(max_length=50, choices=route_optimization_choices,
                                          default=ROUTE_OPTIMIZATION_DISABLED, verbose_name=_('route optimisation'))
    route_optimization_focus = models.CharField(
        max_length=50, choices=route_optimization_focus_choices,
        default=MerchantOptimisationFocus.OLD, verbose_name=_('route optimisation focus'),
        help_text=_('Set, what to focus on for group optimisation. '
                    'This setting is useful only with "route optimisation" enabled.')
    )
    job_service_time = models.PositiveSmallIntegerField(
        choices=job_service_time_choices, default=5,
        help_text=_('Set average duration of time a driver needs to spend to on job site. '
                    'This setting is useful only with "route optimisation" enabled.')
    )
    pickup_service_time = models.PositiveSmallIntegerField(
        choices=job_service_time_choices, default=5,
        help_text=_('Set average duration of time a driver needs to spend to on pickup site. '
                    'This setting is useful only with "route optimisation" enabled.')
    )
    enable_job_capacity = models.BooleanField(default=False)
    enable_clusterization = models.BooleanField(default=True, help_text="Disable this setting if you don't want to see "
                                                                        "clusters of pins on Radaro")
    high_resolution = models.BooleanField(default=False, verbose_name='Enable high resolution images')
    option_barcodes = models.CharField(max_length=8, choices=TYPES_BARCODES, default=TYPES_BARCODES.disable,
                                       verbose_name=_('Barcodes'))
    delivery_interval = models.PositiveSmallIntegerField(default=3, validators=[MaxValueValidator(24), ],
                                                         help_text='Value (in hours) used for calculating '
                                                                   '"time_interval" in SMS/Email to Customer '
                                                                   'about upcoming delivery.')
    low_feedback_value = models.PositiveIntegerField(default=3, help_text="Set the number of stars that should be "
                                                                          "considered as low rating")
    call_center_email = CIEmailField(max_length=50, blank=True)
    email_sender = CIEmailField(
        max_length=50, blank=True,
        help_text='The address for emails sender for all notifications to customers. '
                  'If empty used the default "noreply@radaro.com.au" address.'
    )
    email_sender_name = models.CharField(
        max_length=50, blank=True,
        help_text='The name for emails sender for all notifications to customers. '
                  'If empty used the default "Radaro" name'
    )
    driver_can_create_job = models.BooleanField(default=False, help_text="This setting allows drivers to create "
                                                                         "new jobs and assign them to other drivers.")
    enable_auto_complete_customer_fields = models.BooleanField(
        default=False,
        verbose_name='Auto-complete customer fields when driver creates job',
        help_text='Drivers will get suggestions with customer details once they start typing customer phone or name',
    )
    forbid_drivers_unassign_jobs = models.BooleanField(verbose_name='Forbid drivers to unassign jobs from themselves',
                                                       default=False)
    driver_break_enabled = models.BooleanField(verbose_name='"Take a break" dialogue', default=False,
                                               help_text='This option allows to inform drivers they can take a break')
    driver_break_interval = models.PositiveIntegerField(verbose_name='"Take a break" dialogue appearing interval',
                                                        validators=[MaxValueValidator(24)], blank=True, null=True)
    driver_break_description = models.CharField(verbose_name='"Take a break" dialogue description',
                                                max_length=150, blank=True)
    in_app_jobs_assignment = models.BooleanField(default=False, verbose_name='In-app jobs assignment',
                                                 help_text='Enable ability for drivers to see not assigned '
                                                           'jobs and assign jobs on themselves from the app ')
    notify_of_not_assigned_orders = models.BooleanField(
        default=False, verbose_name='Enable notification of available not assigned orders',
    )
    required_skill_sets_for_notify_orders = models.ManyToManyField(
        'merchant.SkillSet', blank=True, related_name='notifying_merchant',
        verbose_name='Required skill sets for notification of available not assigned orders',
        help_text='A notification will be sent if at least one of the skill sets specified here is on the order.',
    )
    jobs_export_email = CIEmailField(max_length=50, blank=True)
    pod_email = CIEmailField(max_length=50, blank=True, help_text='Email to send proof of delivery')
    customer_review_screen_text = models.TextField(default=get_review_screen_default_text)
    signature_screen_text = models.TextField(
        max_length=100, blank=True, help_text='Confirmation signature'
    )
    pre_inspection_signature_screen_text = models.TextField(
        max_length=100, blank=True, help_text='Pre-inspection signature',
        verbose_name='Pre-inspection signature screen text'
    )
    pickup_signature_screen_text = models.TextField(
        max_length=100, blank=True, help_text='Pick-up confirmation signature'
    )
    job_failure_signature_screen_text = models.TextField(
        max_length=100, blank=True, verbose_name='Fail job signature screen text',
        help_text='Job failure confirmation signature',
    )
    job_failure_screen_text = JSONField(
        default=default_job_failure_screen_text_dict,
        help_text='Text for failed jobs on Customer tracking page',
        verbose_name='Customer tracking screen text at job failure')
    assigned_job_screen_text = JSONField(
        default=default_assigned_job_screen_text_dict,
        verbose_name='Customer tracking screen text about job assigned to the driver')
    not_assigned_job_screen_text = JSONField(
        default=default_not_assigned_job_screen_text_dict,
        verbose_name='Customer tracking screen text about job creation')
    pickup_failure_screen_text = JSONField(
        default=default_job_failure_screen_text_dict,
        help_text='Text for failed jobs on Pickup tracking page',
        verbose_name='Pickup tracking screen text at job failure')
    eta_with_traffic = models.BooleanField(default=False, verbose_name='ETA with traffic information')
    round_corners_for_customer = models.BooleanField(
        default=False, verbose_name='Rounding the logos on the tracking page',
        help_text='Enable the rounding of the companies logos on customer tracking page',
    )

    merchant_type = models.CharField(max_length=15, choices=MerchantTypes.MERCHANT_TYPES,
                                     default=MerchantTypes.MERCHANT_TYPES.DEFAULT)
    survey_export_directory = models.CharField(
        max_length=50, blank=True, verbose_name='Survey export SFTP directory',
        help_text="Path to merchant's survey results folder on SFTP server (e.g. 'delivery/survey_responses/...')"
    )
    enable_saml_auth = models.BooleanField(default=False, verbose_name='Enable SAML auth')

    working_time = models.IntegerField(
        default=8, blank=True, null=True,
        help_text='"Working" time after which the driver will be moved to the "not working" status',
    )

    enable_skids = models.BooleanField(default=False, verbose_name='Enable SKID adjustment')
    default_skid_length = models.FloatField(default=48, verbose_name='default SKID length')
    default_skid_width = models.FloatField(default=48, verbose_name='default SKID width')
    default_skid_height = models.FloatField(default=40, verbose_name='default SKID height')

    enable_concatenated_orders = models.BooleanField(default=False)

    time_today_reminder = models.TimeField(default=datetime.time, verbose_name='Today delivery reminder',
                                           help_text='Time at which today upcoming delivery notification '
                                                     'is sent according to the merchant timezone.')
    forbid_drivers_edit_schedule = models.BooleanField(default=False,
                                                       verbose_name='Restrict drivers from editing schedules')

    signature_or_photo = 0
    signature = 1
    photo = 2

    confirmation_requirement_choices = (
        (signature_or_photo, 'Either signature required or photo required'),
        (signature, 'Signature required and photo optional'),
        (photo, 'Photo required and signature optional'),
    )

    confirmation_requirement = models.IntegerField(
        choices=confirmation_requirement_choices,
        default=DISABLED)

    minimum_confirmation_photos = models.IntegerField(default=0)

    objects = MerchantManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ('name', )

    def __str__(self):
        return u'{name}'.format(name=self.name)

    def _on_logo_change(self, previous):
        if self.logo:
            if self.logo.height > 500:
                self.resize_image(self.logo)
            self.thumbnailer.generate_for('logo')

    @property
    def enable_barcode_before_delivery(self):
        return self.option_barcodes in [self.TYPES_BARCODES.before, self.TYPES_BARCODES.both]

    @property
    def enable_barcode_after_delivery(self):
        return self.option_barcodes in [self.TYPES_BARCODES.both, self.TYPES_BARCODES.after]

    @staticmethod
    def autocomplete_search_fields():
        return "name__icontains", "id__iexact"

    @property
    def advanced_completion_enabled(self):
        return self.advanced_completion != Merchant.ADVANCED_COMPLETION_DISABLED

    @property
    def allow_geofence(self):
        return True if self.geofence_settings else False

    @property
    def geofence_upon_entering(self):
        return True if self.geofence_settings == Merchant.UPON_ENTERING else False

    @property
    def allowed_path_processing(self):
        return self.path_processing == self.ANIMATION_WITH_SNAP_TO_ROADS and config.PATH_IMPROVING

    @property
    def thumb_logo_100x100(self):
        if self.thumb_logo_100x100_field:
            lg = self.thumb_logo_100x100_field
        else:
            lg = self.logo
        try:
            return lg.url
        except:
            return None

    @property
    def is_nti(self):
        return self.merchant_type == MerchantTypes.MERCHANT_TYPES.NTI

    @property
    def use_custom_phone_for_subbranding(self):
        return self.customer_tracking_phone_settings == self.SUBBRAND_PHONE

    @property
    def customer_survey_enabled(self):
        return bool(self.customer_survey_id)

    @property
    def instant_upcoming_delivery_enabled(self):
        return self.templates.filter(
            template_type=MerchantMessageTemplate.INSTANT_UPCOMING_DELIVERY,
            enabled=True
        ).exists()

    @property
    def instant_upcoming_delivery(self):
        return self.templates.filter(
            Q(template_type=MerchantMessageTemplate.INSTANT_UPCOMING_DELIVERY, enabled=True) |
            Q(template_type=MerchantMessageTemplate.UPCOMING_DELIVERY, enabled=False)
        ).count() == 2

    def clean_fields(self, exclude=None):
        if self.phone:
            try:
                phone_is_valid(self.phone, self.countries)
            except ValidationError as exc:
                raise ValidationError({'phone': [exc.message, ]})
        if self.use_custom_phone_for_subbranding and not self.use_subbranding:
            raise ValidationError({
                'customer_tracking_phone_settings': ['You cannot change this option, because subbrandings are unavailable.']
            })
        if self.checklist_id and self.geofence_upon_entering:
            raise ValidationError({
                'geofence_settings': ['You cannot use geofence upon entering together with checklist.']
            })
        if self.use_way_back_status and not self.use_hubs:
            raise ValidationError({
                'use_way_back_status': ['You can\'t use `way back` status without enabling `hubs`']
            })
        if self.route_optimization != self.ROUTE_OPTIMIZATION_DISABLED and not self.use_hubs:
            raise ValidationError({
                'route_optimization': [_('You can\'t use `route optimisation` feature without enabling `hubs`')]
            })
        if self.allow_geofence and self.advanced_completion_enabled:
            raise ValidationError("You cannot enable geofence settings and success codes together.")
        if self.enable_delivery_pre_confirmation and self.allow_geofence:
            raise ValidationError({
                'enable_delivery_pre_confirmation': ["You can't use `pre confirmation` together with geofence."]
            })
        if self.enable_pick_up_confirmation and not self.use_pick_up_status:
            raise ValidationError({
                'enable_pick_up_confirmation': [
                    "You can't use `pick up confirmation` without enabling `use_pick_up_status`."
                ]
            })
        if self.driver_break_enabled and not self.driver_break_interval:
            raise ValidationError({'driver_break_interval': 'You can\'t use "take-a-break" dialogue option '
                                                            'without setting an interval.'})
        if self.id:
            old_countries = Merchant.objects.get(id=self.id).countries
            cur_countries = self.countries
            countries_for_disabling = set(old_countries) - set(cur_countries)
            if len(countries_for_disabling) != 0:
                used_countries = get_used_countries_from_set(self, countries_for_disabling)
                if len(used_countries) != 0:
                    raise ValidationError({
                        'countries': [
                            "You can't disable countr{ending} ({countries}), because you have phones from it." \
                                .format(ending='y' if len(used_countries) == 1 else 'ies',
                                        countries=', '.join(used_countries))
                        ]
                    })

        barcode_scanning_after = self.option_barcodes in [self.TYPES_BARCODES.after, self.TYPES_BARCODES.both]
        if not self.enable_delivery_confirmation and barcode_scanning_after:
            raise ValidationError({
                'option_barcodes': [_('You cannot select an option that requires a barcode scan upon delivery '
                                      'with `enable_delivery_confirmation` disabled')]
            })
        if not self.enable_delivery_confirmation and self.enable_delivery_confirmation_documents:
            raise ValidationError({
                'enable_delivery_confirmation_documents': [_(
                    'You cannot select an option with `enable_delivery_confirmation` disabled')]
            })
        if not self.enable_delivery_confirmation_documents and self.enable_reminder_to_attach_confirmation_documents:
            raise ValidationError({
                'enable_reminder_to_attach_confirmation_documents': [_(
                    'You cannot select an option with `enable_delivery_confirmation_documents` disabled')]
            })
        if not self.in_app_jobs_assignment and self.notify_of_not_assigned_orders:
            raise ValidationError({
                'notify_of_not_assigned_orders': [_(
                    'You cannot select an option with `in_app_jobs_assignment` disabled')]
            })

        super(Merchant, self).clean_fields(exclude)

    def save(self, *args, **kwargs):
        merchant = Merchant.objects.filter(pk=self.pk).first()

        if merchant and merchant.checklist and self.checklist and merchant.checklist_id != self.checklist_id:
            merchant.checklist.resultchecklist_set.filter(is_correct__isnull=True).update(checklist=self.checklist)

        if self.logo and (self.logo.height > 500):
            self.resize_image(self.logo)

        if self.phone:
            self.phone = e164_phone_format(self.phone, self.countries)

        if not self.sms_sender:
            self.sms_sender = self.name[:config.MAX_SMS_SENDER_LENGTH]

        if self.merchant_group:
            self.webhook_url = [self.merchant_group.webhook_url] if self.merchant_group.webhook_url \
                else self.webhook_url
            self.webhook_verification_token = self.merchant_group.webhook_verification_token

        elif self.merchant_group is None and (merchant and merchant.merchant_group):
            self.webhook_verification_token = generate_webhook_verification_token()

        if not merchant:
            self.merchant_identifier = self.generate_identifier(self.name)

        super(Merchant, self).save(*args, **kwargs)

        if merchant and merchant.push_notifications_settings_id != self.push_notifications_settings_id:
            Device.objects.filter(user__merchant=self).update(application_id=self.push_notifications_settings_id)

        if not merchant:
            MerchantMessageTemplate.create_merchant_templates(merchant=self)

    @classmethod
    def generate_identifier(cls, name):
        index, max_merchant_name_length, max_length = 1, 30, 50
        merchant_name, cluster_name = name.replace(' ', ''), settings.CLUSTER_NAME.replace(' ', '_')

        def build(_name, _optional_index, _cluster_name):
            _name = re.sub(r'[^a-zA-Z0-9._-]', '', _name)[:max_merchant_name_length] or 'identifier'
            _cluster_name = re.sub(r'[^a-zA-Z0-9._-]', '', _cluster_name)
            ret_name = '{merchant_name}{optional_index}-{cluster_name}'.format(
                merchant_name=_name, optional_index=_optional_index, cluster_name=_cluster_name
            )
            return ret_name.lower()[:max_length]

        identifier = build(merchant_name, '', cluster_name)
        while cls.objects.filter(merchant_identifier=identifier).exists():
            optional_index = '-%s' % index
            identifier = build(merchant_name, optional_index, cluster_name)
            index += 1
        return identifier

    def change_balance(self, amount):
        update_fields = ['balance', ]
        self.balance = F('balance') + amount
        if self.is_blocked and self.balance > 0:
            self.is_blocked = False
            update_fields.append('is_blocked')
        self.save(update_fields=update_fields)

    def _get_default_price(self, name):
        param_name = 'DEFAULT_' + name + '_COST'
        return getattr(config, param_name)

    @cached_property
    def price_per_job(self):
        if self.job_price is None:
            return self._get_default_price('JOB')
        return self.job_price

    @cached_property
    def price_per_location_processing(self):
        return self.location_processing_price or self._get_default_price('LOCATION_PROCESSING')

    @cached_property
    def price_per_sms(self):
        if self.sms_price is None:
            return self._get_default_price('SMS')
        return self.sms_price

    @cached_property
    def nti_ta_phone(self):
        # Useful only for NTI merchant
        return config.NTI_TA_PHONE

    def regenerate_webhook_verification_token(self):
        self.webhook_verification_token = generate_webhook_verification_token()
        self.save(update_fields=('webhook_verification_token', ))

    def upload_report(self, report_instance):
        if not report_instance.file.size:
            return

        with SFTPMerchantClient(self) as client:
            client.upload_file(report_instance.file, report_instance.file.name.split('/')[-1])

    def send_report_email(self, report_instance, email, template, extra_context=None):
        report_link = report_instance.file.url if report_instance.file.size else ''
        extra_context = extra_context or {}
        extra_context['report_link'] = report_link

        self.send_notification(
            template, merchant_id=self.id,
            send_sms=False, email=email, extra_context=extra_context
        )

    def send_pod_report_email(self, email, attachments=None, extra_context=None):
        extra_context = extra_context or {}
        self.send_notification(
            MessageTemplateStatus.POD_REPORT, merchant_id=self.id,
            send_sms=False, email=email, attachments=attachments, extra_context=extra_context
        )

    def send_sod_issue_email(self, email, attachments=None, extra_context=None):
        extra_context = extra_context or {}
        self.send_notification(
            MessageTemplateStatus.SOD_ISSUE, merchant_id=self.id,
            send_sms=False, email=email, attachments=attachments, extra_context=extra_context
        )

    def send_eod_issue_email(self, email, attachments=None, extra_context=None):
        extra_context = extra_context or {}
        self.send_notification(
            MessageTemplateStatus.EOD_ISSUE, merchant_id=self.id,
            send_sms=False, email=email, attachments=attachments, extra_context=extra_context
        )

    @classmethod
    def get_properties(cls):
        return [name for name in dir(cls) if isinstance(getattr(cls, name), (property, cached_property))]

    @cached_property
    def today(self):
        from django.utils import timezone
        return timezone.now().astimezone(self.timezone).date()


class MerchantGroup(models.Model):
    title = models.CharField(max_length=255)
    webhook_verification_token = models.CharField(max_length=255, default=generate_webhook_verification_token)
    webhook_url = models.CharField(blank=True, max_length=500)
    core_merchant = models.OneToOneField('Merchant', null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return u"Merchant Group: {0}".format(self.title)

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        group = MerchantGroup.objects.filter(id=self.id).first()
        if group and group.webhook_verification_token != self.webhook_verification_token:
            self.set_group_webhook_verification_token()
        if group and group.webhook_url != self.webhook_url:
            self.set_group_webhook_url()
        super(MerchantGroup, self).save(force_insert, force_update, using, update_fields)

    def set_group_webhook_verification_token(self):
        return self.merchants.update(webhook_verification_token=self.webhook_verification_token)

    def set_group_webhook_url(self):
        return self.merchants.update(webhook_url=[self.webhook_url])

    def delete(self, using=None, keep_parents=False):
        merchants = list(self.merchants.all())
        result = super().delete(using, keep_parents)
        for merchant in merchants:
            merchant.refresh_from_db()
            merchant.regenerate_webhook_verification_token()
        return result


__all__ = ['Merchant', 'MerchantGroup', 'default_job_failure_screen_text_dict',
           'default_assigned_job_screen_text_dict', 'default_not_assigned_job_screen_text_dict']
