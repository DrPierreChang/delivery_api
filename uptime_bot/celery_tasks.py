import requests

from delivery.celery import app


@app.task(ignore_result=True, time_limit=30)
def send_pong_to_uptimebot(pong_to):
    requests.get(pong_to)
