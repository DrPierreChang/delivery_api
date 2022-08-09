from __future__ import unicode_literals

import logging
import warnings

from delivery.celery import app

logger = logging.getLogger(__name__)


@app.task()
def notify_about_event_without_content_type(id):
    warnings.warn(f'Event without content type.\nEvent id: {id}.', UserWarning)
