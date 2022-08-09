# Celery
# http://docs.celeryproject.org/en/latest/configuration.html

from delivery.settings import env_vars

from kombu import Exchange, Queue

CELERY_SEND_TASK_ERROR_EMAILS = True
CELERY_BROKER_URL = env_vars.CELERY_BROKER_URL
CELERY_RESULT_BACKEND = env_vars.CELERY_RESULT_BACKEND
CELERY_TASK_DEFAULT_QUEUE = 'delivery-queue'
CELERY_TASK_DEFAULT_EXCHANGE = 'delivery-queue'
CELERY_TASK_DEFAULT_ROUTING_KEY = CELERY_TASK_DEFAULT_QUEUE
CELERY_TASK_PRIORITY_QUEUE = 'delivery-queue-priority'
CELERY_TASK_SLOW_QUEUE = 'delivery-queue-slow'
CELERY_TASK_OPTIMISATION_QUEUE = 'delivery-queue-optimisation'
CELERY_TASK_OPTIMISATION_ENGINE_QUEUE = 'delivery-queue-optimisation-engine'
CELERY_TASK_OPTIMISATION_SLOW_QUEUE = 'delivery-queue-optimisation-slow'
CELERY_TASK_QUEUES = (
    Queue(CELERY_TASK_DEFAULT_QUEUE, Exchange(CELERY_TASK_DEFAULT_EXCHANGE), routing_key=CELERY_TASK_DEFAULT_QUEUE),
    Queue(CELERY_TASK_PRIORITY_QUEUE, Exchange(CELERY_TASK_DEFAULT_EXCHANGE), routing_key=CELERY_TASK_PRIORITY_QUEUE),
    Queue(CELERY_TASK_SLOW_QUEUE, Exchange(CELERY_TASK_DEFAULT_EXCHANGE), routing_key=CELERY_TASK_SLOW_QUEUE),
    Queue(CELERY_TASK_OPTIMISATION_QUEUE, Exchange(CELERY_TASK_DEFAULT_EXCHANGE),
          routing_key=CELERY_TASK_OPTIMISATION_QUEUE),
    Queue(CELERY_TASK_OPTIMISATION_ENGINE_QUEUE, Exchange(CELERY_TASK_DEFAULT_EXCHANGE),
          routing_key=CELERY_TASK_OPTIMISATION_ENGINE_QUEUE),
    Queue(CELERY_TASK_OPTIMISATION_SLOW_QUEUE, Exchange(CELERY_TASK_DEFAULT_EXCHANGE),
          routing_key=CELERY_TASK_OPTIMISATION_SLOW_QUEUE)
)
CELERY_TIMEZONE = 'Australia/Melbourne'
CELERY_TASK_SERIALIZER = 'pickle'
CELERY_RESULT_SERIALIZER = 'pickle'
CELERY_ACCEPT_CONTENT = {'pickle'}
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_ROUTES = {}

if CELERY_BROKER_URL.startswith('rediss://') or CELERY_RESULT_BACKEND.startswith('rediss://'):
    import ssl

    CELERY_REDIS_BACKEND_USE_SSL = {
        'ssl_cert_reqs': ssl.CERT_NONE,
    }

# Setup CELERY_TASK_ROUTES setting for celery
TASK_ROUTES_SETTINGS = {
    CELERY_TASK_PRIORITY_QUEUE: [
        'driver.celery_tasks.process_new_location',
        'notification.celery_tasks.send_device_notification',
        'notification.celery_tasks.send_template_notification',
        'uptime_bot.celery_tasks.send_pong_to_uptimebot'
    ],
    CELERY_TASK_SLOW_QUEUE: [
        'tasks.celery_tasks.base.fail_outdated_in_progress_jobs',
        'tasks.celery_tasks.base.generate_driver_path',
        'tasks.celery_tasks.base.remind_about_customer_rating',
        'tasks.celery_tasks.base.remind_about_upcoming_delivery',
        'merchant.celery_tasks.send_reports',
        'merchant.celery_tasks.send_merchant_jobs_report',
        'merchant.celery_tasks.send_sub_brand_jobs_report',
        'merchant.celery_tasks.send_merchant_survey_report',
        'merchant.celery_tasks.send_sub_brand_survey_report',
        'webhooks.celery_tasks.send_external_job_event',
    ],
    CELERY_TASK_OPTIMISATION_QUEUE: [
        'route_optimisation.celery_tasks.optimisation.handle_results',
        'route_optimisation.celery_tasks.optimisation.run_advanced_optimisation',
        'route_optimisation.celery_tasks.optimisation.run_optimisation_refresh',
        'route_optimisation.celery_tasks.optimisation.run_small_optimisation',
    ],
    CELERY_TASK_OPTIMISATION_ENGINE_QUEUE: [
        'route_optimisation.celery_tasks.optimisation.optimisation_engine_run',
    ],
    CELERY_TASK_OPTIMISATION_SLOW_QUEUE: [
        'route_optimisation.celery_tasks.remove_route_point_task.remove_route_point',
    ]
}
for queue_key, tasks_names in list(TASK_ROUTES_SETTINGS.items()):
    for task_name in tasks_names:
        CELERY_TASK_ROUTES[task_name] = {
            'queue': queue_key,
            'routing_key': queue_key,
        }
