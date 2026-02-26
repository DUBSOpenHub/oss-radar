"""APScheduler daemon for OSS Radar background scheduling."""

from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from radar.config import Settings

logger = logging.getLogger(__name__)


class RadarScheduler:
    """Wraps APScheduler BlockingScheduler with daily + weekly cron jobs."""

    def __init__(self, config: Settings) -> None:
        self.config = config
        self._scheduler = BlockingScheduler(timezone="UTC")

    def start(self) -> None:
        """Register jobs and start the blocking scheduler."""
        self._register_daily()
        self._register_weekly()
        logger.info(
            "scheduler_starting",
            extra={
                "daily_cron": self.config.daily_cron,
                "weekly_cron": self.config.weekly_cron,
            },
        )
        self._scheduler.start()

    def stop(self) -> None:
        """Shut down the scheduler gracefully."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _register_daily(self) -> None:
        cron_parts = self.config.daily_cron.split()
        if len(cron_parts) != 5:
            raise ValueError(f"Invalid daily_cron: {self.config.daily_cron!r}")

        minute, hour, day, month, day_of_week = cron_parts
        self._scheduler.add_job(
            func=self._run_daily,
            trigger=CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
                timezone="UTC",
            ),
            id="daily_report",
            name="OSS Radar Daily Report",
            replace_existing=True,
        )
        logger.info("job_registered", extra={"job": "daily_report"})

    def _register_weekly(self) -> None:
        cron_parts = self.config.weekly_cron.split()
        if len(cron_parts) != 5:
            raise ValueError(f"Invalid weekly_cron: {self.config.weekly_cron!r}")

        minute, hour, day, month, day_of_week = cron_parts
        self._scheduler.add_job(
            func=self._run_weekly,
            trigger=CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
                timezone="UTC",
            ),
            id="weekly_digest",
            name="OSS Radar Weekly Digest",
            replace_existing=True,
        )
        logger.info("job_registered", extra={"job": "weekly_digest"})

    def _run_daily(self) -> None:
        """Execute the daily pipeline (imported lazily to avoid circular imports)."""
        try:
            from radar.pipeline import PipelineOrchestrator
            from radar.storage.database import Database

            db = Database(self.config.db_path)
            pipeline = PipelineOrchestrator(config=self.config, db=db)
            pipeline.run_daily()
        except Exception as exc:
            logger.error("scheduled_daily_failed", extra={"error": str(exc)}, exc_info=True)

    def _run_weekly(self) -> None:
        """Execute the weekly pipeline."""
        try:
            from radar.pipeline import PipelineOrchestrator
            from radar.storage.database import Database

            db = Database(self.config.db_path)
            pipeline = PipelineOrchestrator(config=self.config, db=db)
            pipeline.run_weekly()
        except Exception as exc:
            logger.error("scheduled_weekly_failed", extra={"error": str(exc)}, exc_info=True)
