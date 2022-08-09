from datetime import timedelta

from model_utils import Choices

OPTIMISATION_TYPES = Choices(
    ('SOLO', 'Solo'),
    ('FAST', 'Fast'),
    ('ADVANCED', 'Advanced'),
    ('SCHEDULED', 'Scheduled'),
    ('PTV_EXPORT', 'PTV Export'),
)

REFRESH_SOLO = 'refresh_solo'
REFRESH_ADVANCED = 'refresh_advanced'


class MerchantOptimisationTypes:
    PTV = 'ptv'
    PTV_SMARTOUR_EXPORT = 'ptv_smartour_export'
    OR_TOOLS = 'or-tools'


class MerchantOptimisationFocus:
    MINIMAL_TIME = 'minimal_time'
    TIME_BALANCE = 'time_balance'
    ALL = 'all'
    OLD = 'old'


class HubOptions:
    BASE_START_HUB = Choices(
        ('default_hub', 'Driver\'s default hub'),
        ('default_point', 'Driver\'s default point'),
        ('job_location', 'Start job location'),
        ('hub_location', 'Merchant\'s hub'),
    )
    BASE_END_HUB = Choices(
        ('default_hub', 'Driver\'s default hub'),
        ('default_point', 'Driver\'s default point'),
        ('job_location', 'End job location'),
        ('hub_location', 'Merchant\'s hub'),
    )

    START_HUB = BASE_START_HUB + Choices(
        ('driver_location', 'Driver\'s location'),
    )
    END_HUB = BASE_END_HUB + Choices(
        ('driver_location', 'Driver\'s location'),
    )

    EXTERNAL_START_HUB = BASE_START_HUB
    EXTERNAL_END_HUB = BASE_END_HUB


CONTEXT_HELP_ITEM = 'help_data'


class GroupConst:
    ALL = 'all'
    FAILED = 'failed'
    SCHEDULED = 'scheduled'
    CURRENT = 'current'


# Don't forget to increase GOOGLE_API_REQUESTS_LIMIT in case MAX_JOBS_COUNT will be >800
MAX_JOBS_COUNT = 1300
GOOGLE_API_REQUESTS_LIMIT = 40000


class RoutePointKind:
    HUB = 'hub'
    LOCATION = 'location'
    PICKUP = 'pickup'
    DELIVERY = 'delivery'
    BREAK = 'break'


# Here are constants from old version of route optimisation
class OldROConstants:
    PTV = 'ptv'
    PTV_SMARTOUR_EXPORT = 'ptv_smartour_export'
    OR_TOOLS = 'or-tools'
    PERIOD_SOLO_OPTIMIZATION = timedelta(hours=40)
    ORDERS_FOR_SOLO_OPTIMIZATION = 23
    ORDERS_FOR_GENERAL_OPTIMIZATION = 100
