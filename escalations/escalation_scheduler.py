"""
escalations/escalation_scheduler.py — APScheduler integration for escalation engine
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from escalations.escalation_engine import EscalationEngine
from configs.base import BaseConfig

logger = logging.getLogger(__name__)
config = BaseConfig()

scheduler = AsyncIOScheduler()
engine = EscalationEngine()


def start_escalation_scheduler():
    """Start the background escalation scheduler."""
    scheduler.add_job(
        engine.run,
        trigger=IntervalTrigger(minutes=config.ESCALATION_INTERVAL_MINUTES),
        id="escalation_scan",
        name="Escalation Engine Scan",
        replace_existing=True,
        misfire_grace_time=60,
    )
    scheduler.start()
    logger.info(
        "Escalation scheduler started | interval=%d min",
        config.ESCALATION_INTERVAL_MINUTES,
    )


def stop_escalation_scheduler():
    """Gracefully stop the scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Escalation scheduler stopped")
