"""Scheduler for evaluation, reconciliation and the job worker (spec 7)."""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from florque_client.app import FlorqueApp

log = logging.getLogger("florque.scheduler")


def start_scheduler(
    app: FlorqueApp, evaluate_minutes: int = 15, worker_seconds: int = 10
) -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="UTC")
    hub = app.hub
    sched.add_job(
        lambda: hub.enqueue("evaluate"), "interval", minutes=evaluate_minutes, id="enqueue_evaluate"
    )
    sched.add_job(
        lambda: hub.enqueue("reconcile"), "cron", hour=3, minute=0, id="enqueue_reconcile"
    )

    def work() -> None:
        try:
            out = hub.run_jobs_once()
            if out["jobs"]:
                log.info("jobs", extra={"status": len(out["jobs"])})
        except Exception:  # noqa: BLE001
            log.exception("worker failed")

    sched.add_job(
        work, "interval", seconds=worker_seconds, id="worker", max_instances=1, coalesce=True
    )
    sched.start()
    return sched
