"""Prometheus /metrics (API_FORENSICS.md Section 3).

Request count/latency/in-progress gauges come for free from
prometheus-fastapi-instrumentator (wired up in main.py). The one thing it
can't give us is Celery task outcomes -- those happen in separate worker
processes, so an in-process Counter here would only ever read zero. Instead,
celery_app.py's task_failure/task_success handlers INCR
metrics:celery:{failed,success}:{task_name} in Redis (already the broker,
no new datastore) on every task completion, and this collector reads those
keys back at scrape time, whichever process happens to be scraped.
"""
from prometheus_client.core import GaugeMetricFamily

from app.utils.redis_client import redis_client

_COUNTERS = {
    "celery_task_failed_total": "metrics:celery:failed:",
    "celery_task_success_total": "metrics:celery:success:",
}


class CeleryTaskCounterCollector:
    def collect(self):
        for metric_name, key_prefix in _COUNTERS.items():
            outcome = "failures" if "failed" in metric_name else "successes"
            family = GaugeMetricFamily(
                metric_name,
                f"Celery task {outcome} by task name, tallied in Redis by celery_app.py's task signal handlers.",
                labels=["task_name"],
            )
            try:
                for key in redis_client.scan_iter(match=f"{key_prefix}*"):
                    task_name = key[len(key_prefix):]
                    value = redis_client.get(key)
                    family.add_metric([task_name], float(value or 0))
            except Exception:
                pass  # /metrics must never 500 because Redis hiccuped
            yield family
