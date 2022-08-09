from __future__ import absolute_import, unicode_literals

from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.contrib.staticfiles.storage import staticfiles_storage
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.functional import empty
from django.utils.timezone import now

from model_utils import FieldTracker

from custom_auth.models import ApplicationUser, ApplicationUserManager
from driver.models.mixins import MemberImprovePathMixin
from driver.push_messages.composers import ForceOfflinePushMessage
from driver.utils import DEFAULT_DRIVER_STATUS, DRIVER_STATUSES_PARAMS, WorkStatus
from merchant.image_specs import ThumbnailGenerator
from merchant.models import SkillSet
from merchant.models.mixins import MerchantSendNotificationMixin
from radaro_router.mixins import RouterCheckInstanceMixin
from radaro_router.models import RadaroRouterRelationMixin
from radaro_utils.files.utils import get_upload_path
from radaro_utils.models import ResizeImageMixin
from radaro_utils.radaro_model_utils.mixins import TrackMixin
from radaro_utils.radaro_phone.models import PhoneField
from radaro_utils.radaro_phone.utils import e164_phone_format, phone_is_valid
from reporting.models import Event
from reporting.signals import create_event

from ..mixins import TrackModelChangesMixin
from ..models import Car
from ..utils import MerchantFieldCallControl, generate_id, get_upload_path_100x100


class BaseMemberQuerySet(models.QuerySet):
    def not_deleted(self):
        return self.filter(deleted=False)

    def active(self):
        return self.filter(is_active=True)

    def deleted_or_active(self):
        return self.filter(Q(deleted=True) | Q(is_active=True))

    def drivers(self):
        return self.filter(role__in=[Member.DRIVER, Member.MANAGER_OR_DRIVER])

    def managers(self):
        return self.filter(role__gte=Member.MANAGER)


class AllMembersManager(ApplicationUserManager):
    def __init__(self):
        super().__init__()
        self._queryset_class = BaseMemberQuerySet


class MembersManager(AllMembersManager):
    def get_queryset(self):
        return super().get_queryset().not_deleted().select_related('merchant').prefetch_related('merchants')


class DriverQuerySet(BaseMemberQuerySet):
    def add_statuses(self):
        from driver.queries import QUERY_ANNOTATION
        return self.annotate(_status=QUERY_ANNOTATION)

    def sort_by_status(self):
        from driver.queries import SORT_ANNOTATION
        return self.annotate(_status_sort_rate=SORT_ANNOTATION).order_by('deleted', '_status_sort_rate', 'id')

    def filter_by_is_online(self, value):
        if value:
            return self.filter(work_status=WorkStatus.WORKING)
        else:
            return self.exclude(work_status=WorkStatus.WORKING)

    def filter_by_is_online_for_manager(self, value):
        if value:
            return self.filter(work_status=WorkStatus.WORKING, is_offline_forced=False)
        else:
            return self.exclude(work_status=WorkStatus.WORKING, is_offline_forced=False)

    def filter_by_work_status_for_manager(self, value):
        if value == WorkStatus.NOT_WORKING:
            return self.filter(Q(work_status=WorkStatus.NOT_WORKING) | Q(is_offline_forced=True))
        else:
            return self.filter(work_status=value, is_offline_forced=False)

    def prefetch_sod_checklist_result(self, merchant):
        from merchant_extension.models import Checklist, ResultChecklist
        qs = ResultChecklist.objects.filter(checklist__checklist_type=Checklist.START_OF_DAY)
        qs = qs.filter_today_checklists(merchant.timezone)
        prefetch = models.Prefetch('resultchecklist_set', queryset=qs, to_attr='sod_checklists')
        return self.prefetch_related(prefetch)

    def prefetch_eod_checklist_result(self, merchant):
        from merchant_extension.models import Checklist, ResultChecklist
        qs = ResultChecklist.objects.filter(checklist__checklist_type=Checklist.END_OF_DAY)
        qs = qs.filter_today_checklists(merchant.timezone)
        prefetch = models.Prefetch('resultchecklist_set', queryset=qs, to_attr='eod_checklists')
        return self.prefetch_related(prefetch)


class DriversManager(AllMembersManager):
    def __init__(self):
        super().__init__()
        self._queryset_class = DriverQuerySet

    def get_queryset(self):
        return super().get_queryset().drivers().select_related('merchant')


class ActiveDriversManager(DriversManager):
    def get_queryset(self):
        return super().get_queryset().not_deleted().active()


class ActiveDriversManagerWithStatuses(ActiveDriversManager):
    def get_queryset(self):
        return super().get_queryset().add_statuses()


class ManagersManager(AllMembersManager):
    def get_queryset(self):
        return super().get_queryset().not_deleted().managers().select_related('merchant').prefetch_related('merchants')


class Member(MerchantFieldCallControl, MemberImprovePathMixin, ResizeImageMixin, MerchantSendNotificationMixin,
             RouterCheckInstanceMixin, RadaroRouterRelationMixin, TrackModelChangesMixin, TrackMixin, ApplicationUser):
    NOT_DEFINED = 0
    ADMIN = 32
    MANAGER = 16
    GROUP_MANAGER = 8
    SUB_MANAGER = 4
    OBSERVER = 2
    DRIVER = 1
    MANAGER_OR_DRIVER = MANAGER | DRIVER

    ROLES_WITH_MANY_MERCHANTS = [MANAGER, ADMIN, OBSERVER]

    search_entries = GenericRelation(
        'watson.SearchEntry',
        content_type_field='content_type',
        object_id_field='object_id_int',
        related_query_name='members_search_entries',
    )

    positions = (
        (ADMIN, 'Admin Manager'),
        (MANAGER, 'Manager'),
        (GROUP_MANAGER, 'Group manager'),
        (SUB_MANAGER, 'Sub brand manager'),
        (DRIVER, 'Driver'),
        (MANAGER_OR_DRIVER, 'Manager / Driver'),
        (OBSERVER, 'Observer'),
        (NOT_DEFINED, 'OUT_OF_ROLE')
    )

    work_status_choices = (
        (WorkStatus.WORKING, 'Working'),
        (WorkStatus.NOT_WORKING, 'Not working'),
        (WorkStatus.ON_BREAK, 'On break'),
    )

    thumbnailer = ThumbnailGenerator({'avatar': 'thumb_avatar_100x100_field'})

    tracker = FieldTracker(fields=['avatar'])
    track_fields = {'avatar'}

    trackable_fields = ('username', 'phone', 'email')
    check_fields = ('username', 'email')

    member_id = models.PositiveIntegerField(unique=True, db_index=True)
    phone = PhoneField()
    avatar = models.ImageField(null=True, blank=True, upload_to=get_upload_path)
    thumb_avatar_100x100_field = models.ImageField(null=True, blank=True, editable=False,
                                                   upload_to=get_upload_path_100x100)
    language = models.CharField(max_length=10, choices=settings.LANGUAGES, default=settings.USER_DEFAULT_LANGUAGE_CODE,
                                help_text='Application language')
    merchant = models.ForeignKey('merchant.Merchant', null=True, blank=True, on_delete=models.PROTECT)
    sub_branding = models.ForeignKey('merchant.SubBranding', null=True, blank=True, on_delete=models.PROTECT)

    merchants = models.ManyToManyField('merchant.Merchant', blank=True, related_name='group_managers',
                                       verbose_name='Group manager merchants',
                                       help_text='Choose merchant accounts that will be available for the manager.')
    sub_brandings = models.ManyToManyField('merchant.SubBranding', blank=True, related_name='group_managers',
                                           verbose_name='Group manager sub-brandings')
    show_only_sub_branding_jobs = models.BooleanField(
        default=False, verbose_name='Show only sub-brandings jobs',
        help_text='Setting for Group Manager page. Show only sub-brandings jobs in case chosen merchant has jobs '
                  'with and without sub-brandings.',

    )

    car = models.OneToOneField('Car', null=True, blank=True, on_delete=models.SET_NULL)
    work_status = models.CharField(default=WorkStatus.NOT_WORKING, choices=work_status_choices, max_length=15)
    has_internet_connection = models.BooleanField(default=False)
    is_offline_forced = models.BooleanField(default=False)
    last_ping = models.DateTimeField(blank=True, null=True)
    role = models.PositiveIntegerField(default=NOT_DEFINED, choices=positions)
    skill_sets = models.ManyToManyField(SkillSet, related_name='drivers', blank=True)
    last_location = models.ForeignKey('driver.DriverLocation', null=True, blank=True, related_name='last_driver',
                                      on_delete=models.SET_NULL)
    starting_point = models.ForeignKey('merchant.HubLocation', related_name='member_starting', null=True, blank=True,
                                       on_delete=models.PROTECT)
    starting_hub = models.ForeignKey('merchant.Hub', related_name='member_starting', null=True, blank=True,
                                     on_delete=models.PROTECT)
    ending_point = models.ForeignKey('merchant.HubLocation', related_name='member_ending', null=True, blank=True,
                                     on_delete=models.PROTECT)
    ending_hub = models.ForeignKey('merchant.Hub', related_name='member_ending', null=True, blank=True,
                                   on_delete=models.PROTECT)
    events = GenericRelation('reporting.Event', related_query_name='members')
    deleted_at = models.DateTimeField(null=True, blank=True, default=None)
    deleted = models.BooleanField(default=False)

    objects = MembersManager()
    drivers = ActiveDriversManager()
    drivers_with_statuses = ActiveDriversManagerWithStatuses()
    all_drivers = DriversManager()
    managers = ManagersManager()
    all_objects = AllMembersManager()

    class Meta:
        verbose_name = 'member'

    def __str__(self):
        return u'{role} {name}'.format(role=self.get_role_display(), name=self.get_full_name())

    @classmethod
    def member_id_comparator(cls, _id):
        return cls.objects.filter(member_id=_id).exists()

    @staticmethod
    def autocomplete_search_fields():
        return "first_name__icontains", "last_name__icontains", "email__icontains", "phone__icontains", \
               "member_id__iexact", "id__iexact"

    # This method is called from TrackMixin.save
    def _on_avatar_change(self, previous):
        if self.avatar:
            if self.avatar.height > 500:
                self.resize_image(self.avatar)
            self.thumbnailer.generate_for('avatar')
        else:
            if self.is_driver:
                if staticfiles_storage.exists(settings.DEFAULT_DRIVER_ICON):
                    with staticfiles_storage.open(settings.DEFAULT_DRIVER_ICON) as f:
                        self.avatar.save('name.png', f, save=False)
            self.thumb_avatar_100x100_field = self.avatar

    def should_notify(self):
        if not self.avatar and self.is_driver:
            # Simulates the 'avatar' field change event that calls the '_on_avatar_change' method
            return {'avatar'}
        return set()

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.email

        if not self.member_id:
            self.member_id = generate_id(length=7, cmpr=self.__class__.member_id_comparator)

        if self.is_driver and not self.car:
            car = Car.objects.create()
            self.car = car

        if not self.deleted:
            self.deleted_at = None
            if self.phone and self.current_merchant:
                self.phone = e164_phone_format(phone=self.phone, regions=self.current_merchant.countries)

        with MerchantFieldCallControl.allow_field_call():
            super(Member, self).save(*args, **kwargs)

    @property
    def is_online(self):
        return self.work_status == WorkStatus.WORKING

    # Add role if new role is larger, and reset to new role if new role is less
    def set_merchant_position(self, role):
        if role > self.role:
            self.role |= role
        else:
            self.role = role
        self.save()

    def set_availability_status(self, status, initiator=None):
        if initiator is None:
            initiator = self

        forced = True if (initiator.id != self.id and status == WorkStatus.NOT_WORKING) else False
        self.is_offline_forced = forced

        if not forced or self.has_internet_connection:
            self.work_status = status
            Member.objects.filter(id=self.id).update(work_status=status, is_offline_forced=forced)
            if forced:
                self.send_versioned_push(ForceOfflinePushMessage(self, initiator))
        else:
            Member.objects.filter(id=self.id).update(is_offline_forced=forced)

    @property
    def merchant_position(self):
        if not self.positions:
            return self._get_role_display()
        return self.get_role_display()

    @property
    def current_role(self):
        if not self.is_manager_or_driver:
            return self.role

        current_role = getattr(self, '_current_role', None)
        if current_role is not None:
            return current_role

        positions_dict = dict(self.positions)
        from radaro_utils.middlewares.merchant import from_headers
        if from_headers.role is not empty and from_headers.role == positions_dict[self.MANAGER_OR_DRIVER]:
            self._current_role = self.MANAGER
        elif from_headers.role is empty:
            self._current_role = self.DRIVER
        else:
            self._current_role = self.role

        return self._current_role

    def get_manager_who_offline_driver(self):
        if not self.is_offline_forced:
            return None
        driver_ct = ContentType.objects.get_for_model(Member)
        events = Event.objects.filter(object_id=self.id, content_type=driver_ct, event=Event.CHANGED)
        event = events.filter(field='is_offline_forced').order_by('-created_at').first()
        return event.initiator if event and event.new_value == 'True' else None

    def set_last_ping(self):
        old_last_ping = self.last_ping
        self.last_ping = now()

        if not self.has_internet_connection:
            old_dict = {'last_ping': old_last_ping, 'has_internet_connection': self.has_internet_connection}
            new_dict = {'last_ping': self.last_ping, 'has_internet_connection': True}
            initiator = self

            if self.is_offline_forced and self.work_status != WorkStatus.NOT_WORKING:
                old_dict['work_status'] = self.work_status
                self.work_status = WorkStatus.NOT_WORKING
                new_dict['work_status'] = WorkStatus.NOT_WORKING
                initiator = self.get_manager_who_offline_driver() or initiator
                self.send_versioned_push(ForceOfflinePushMessage(self, initiator))

            Member.objects.filter(id=self.id).update(**new_dict)

            create_event(
                old_dict, new_dict, initiator=initiator, instance=self, sender=self,
                track_change_event=('has_internet_connection', 'work_status', 'is_online')
            )

        else:
            Member.objects.filter(id=self.id).update(last_ping=self.last_ping)

    @staticmethod
    def calculate_work_status_for_manager(work_status, is_offline_forced):
        if is_offline_forced:
            return WorkStatus.NOT_WORKING
        return work_status

    def get_work_status_for_manager(self):
        return self.calculate_work_status_for_manager(self.work_status, self.is_offline_forced)

    def get_is_online_for_manager(self):
        if self.is_offline_forced:
            return False
        return self.is_online

    @property
    def is_admin(self):
        return bool(self.role & self.ADMIN)

    @property
    def is_manager(self):
        return bool(self.current_role & self.MANAGER)

    @property
    def is_submanager(self):
        return bool(self.role & self.SUB_MANAGER)

    @property
    def is_group_manager(self):
        return bool(self.role & self.GROUP_MANAGER)

    @property
    def is_driver(self):
        return bool(self.current_role & self.DRIVER)

    @property
    def is_observer(self):
        return bool(self.role & self.OBSERVER)

    @property
    def is_manager_or_driver(self):
        return bool(self.role & self.MANAGER) and bool(self.role & self.DRIVER)

    @property
    def thumb_avatar_100x100(self):
        if self.thumb_avatar_100x100_field:
            av = self.thumb_avatar_100x100_field
        else:
            av = self.avatar
        try:
            return av.url
        except:
            return None

    @property
    def need_email_confirmation(self):
        return self.role >= Member.MANAGER

    @property
    def status(self):
        _status = getattr(self, '_status', None)
        if _status is not None:
            return _status
        else:
            for item in DRIVER_STATUSES_PARAMS:
                if self.order_set.filter(**item['order_attributes']).exists():
                    return item['status']
            return DEFAULT_DRIVER_STATUS

    @property
    def location(self):
        return self.last_location

    def clean_fields(self, exclude=None):
        if not self.deleted and self.current_merchant:
            try:
                phone_is_valid(self.phone, self.current_merchant.countries)
            except ValidationError as exc:
                raise ValidationError({'phone': [exc.message, ]})

        if self.is_submanager and not self.sub_branding:
            raise ValidationError({'sub_branding': 'The sub-manager must have subbranding'})

        if not self.is_submanager and self.sub_branding:
            self.sub_branding = None

        if self.current_merchant and self.sub_branding and self.current_merchant_id != self.sub_branding.merchant_id:
            raise ValidationError({'sub_branding': 'The subbrand must match the merchant.'})

    def on_force_login(self, device_id):
        from custom_auth.push_messages.composers import ForceLogoutPushMessage
        self.user_auth_tokens.all().delete()
        user_devices = self.device_set.exclude(Q(apnsdevice__device_id=device_id) |
                                               Q(gcmdevice__device_id=device_id))
        self.send_versioned_push(ForceLogoutPushMessage(self), exclude_devices=(device_id,))
        user_devices.update(in_use=False)

    @property
    def current_merchant(self):
        with MerchantFieldCallControl.allow_field_call():
            original_merchant = self.merchant

        if not (self.is_admin or self.is_manager or self.is_observer):
            return original_merchant

        current_merchant = getattr(self, '_current_merchant', None)
        if current_merchant is not None:
            return current_merchant

        self._current_merchant = original_merchant
        from radaro_utils.middlewares.merchant import from_headers

        if from_headers.merchant_id is not None and self.id is not None:
            possibly_current_merchant = self.merchants.filter(id=from_headers.merchant_id).first()
            if possibly_current_merchant is not None:
                self._current_merchant = possibly_current_merchant

        from_headers.merchant_id = self._current_merchant.id
        return self._current_merchant

    @current_merchant.setter
    def current_merchant(self, new_merchant):
        self.merchant = new_merchant
        self._current_merchant = new_merchant

        from radaro_utils.middlewares.merchant import from_headers
        from_headers.merchant_id = new_merchant.id

    @property
    def current_merchant_id(self):
        with MerchantFieldCallControl.allow_field_call():
            original_merchant_id = self.merchant_id

        if not (self.is_admin or self.is_manager or self.is_observer):
            return original_merchant_id

        return self.current_merchant.id

    def safe_delete(self):
        from django.db.models.signals import pre_delete
        pre_delete.send(sender=Member, instance=self, using=None)
        # Through this signal, the member is deleted from the router

        self.first_name = 'Deleted'
        self.last_name = 'Driver' if self.is_driver else 'Member'

        self.avatar = None
        self.thumb_avatar_100x100_field = None

        self.password = ''
        self.username = get_random_string(50)
        self.email = get_random_string(50) + '@fake-email.com'
        self.phone = 'deleted'
        self.deleted_at = timezone.now()
        self.deleted = True
        self.is_active = False
        self.work_status = WorkStatus.NOT_WORKING
        self.save()

        self.user_auth_tokens.all().delete()
        self.device_set.all().delete()
