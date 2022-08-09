class MessageTemplateStatus(object):

    ANOTHER = 0
    CUSTOMER_JOB_STARTED = 1
    CUSTOMER_JOB_TERMINATED = 2
    FOLLOW_UP = 3
    FOLLOW_UP_REMINDER = 4
    DRIVER_JOB_STARTED = 5
    COMPLETE_INVITATION = 6
    INVITATION = 7
    CONFIRM_ACCOUNT = 8
    RESET_PASSWORD = 9
    BILLING = 10
    ACCOUNT_LOCKED = 11
    LOW_FEEDBACK = 12
    UPCOMING_DELIVERY = 13
    WEEKLY_REPORT = 14
    ADVANCED_COMPLETION = 15
    JOBS_DAILY_REPORT = 16
    POD_REPORT = 17
    SOD_ISSUE = 18
    INSTANT_UPCOMING_DELIVERY = 19
    SPECIAL_MIELE_SURVEY = 20
    SURVEY_REPORT = 21
    UPCOMING_PICK_UP = 22
    RO_UPCOMING_DELIVERY = 23
    TODAY_UPCOMING_DELIVERY = 24
    EOD_ISSUE = 25

    types = (
        (ANOTHER, 'Another', 'base/another_type'),
        (CUSTOMER_JOB_STARTED, 'Customer job started', 'order/customer_order'),
        (CUSTOMER_JOB_TERMINATED, 'Customer job terminated', 'order/customer_order_terminated'),
        (FOLLOW_UP, 'Reminder (1h)', 'order/customer_order_rating'),
        (FOLLOW_UP_REMINDER, 'Reminder (24h)', 'order/customer_order_rating_reminder'),
        (DRIVER_JOB_STARTED, 'Driver job started', 'order/driver_order'),
        (COMPLETE_INVITATION, 'Complete invitation', 'invitations/complete_invitation'),
        (INVITATION, 'Invitation', 'invitations/invitation'),
        (CONFIRM_ACCOUNT, 'Confirm account', 'email/confirm_account/confirm_account'),
        (RESET_PASSWORD, 'Reset password', 'email/reset_password/reset_password'),
        (BILLING, 'Billing', 'billing/billing'),
        (ACCOUNT_LOCKED, 'Account locked', 'merchant/account_lock'),
        (LOW_FEEDBACK, 'Low customer feedback', 'merchant/low_feedback'),
        (UPCOMING_DELIVERY, 'Upcoming delivery', 'order/customer_order_upcoming_delivery'),
        (INSTANT_UPCOMING_DELIVERY, 'Instant upcoming delivery', 'order/customer_order_instant_upcoming_delivery'),
        (WEEKLY_REPORT, 'Weekly Radaro usage report', 'base/weekly_report'),
        (ADVANCED_COMPLETION, 'Advanced completion', 'order/advanced_completion'),
        (JOBS_DAILY_REPORT, 'Jobs daily report', 'order/jobs_daily_report'),
        (POD_REPORT, 'Proof of delivery report', 'order/pod_report'),
        (SOD_ISSUE, 'Start of Day checklist answer issue', 'checklist/sod_issue'),
        (SPECIAL_MIELE_SURVEY, 'Miele customer survey', 'survey/miele_survey'),
        (SURVEY_REPORT, 'Survey report', 'survey/survey_report'),
        (UPCOMING_PICK_UP, 'Upcoming pick up', 'order/pickup_order'),
        (RO_UPCOMING_DELIVERY, 'Route optimisation upcoming delivery', 'route_optimisation/ro_upcoming_delivery'),
        (TODAY_UPCOMING_DELIVERY, "Upcoming delivery today", 'order/customer_order_today_upcoming_delivery'),
        (EOD_ISSUE, 'End of Day checklist answer issue', 'checklist/eod_issue'),
    )

    template_names_map = {item[0]: item[2] for item in types}
    types_choices = [(item[0], item[1]) for item in types]
    types_map = {k: v.lower().replace(' ', '_') for k, v in types_choices}

    merchant_customizable_templates = [
        CUSTOMER_JOB_STARTED, CUSTOMER_JOB_TERMINATED, FOLLOW_UP,
        FOLLOW_UP_REMINDER, LOW_FEEDBACK, UPCOMING_DELIVERY,
        INSTANT_UPCOMING_DELIVERY, ADVANCED_COMPLETION, JOBS_DAILY_REPORT,
        POD_REPORT, SOD_ISSUE, SURVEY_REPORT, UPCOMING_PICK_UP,
        RO_UPCOMING_DELIVERY, TODAY_UPCOMING_DELIVERY, EOD_ISSUE,
    ]
    enabled_by_default = [
        CUSTOMER_JOB_STARTED, CUSTOMER_JOB_TERMINATED, FOLLOW_UP, COMPLETE_INVITATION,
        INVITATION, CONFIRM_ACCOUNT, RESET_PASSWORD, BILLING, ACCOUNT_LOCKED, ADVANCED_COMPLETION,
    ]


__all__ = ['MessageTemplateStatus', ]
