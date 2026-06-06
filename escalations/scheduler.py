import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from configs.base import settings

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def _job():
    from backend.app.core.database import AsyncSessionLocal
    from escalations.escalation_engine import run_escalation_check

    try:
        async with AsyncSessionLocal() as db:
            await run_escalation_check(db)
    except (OperationalError, SQLAlchemyError, OSError) as exc:
        logger.warning(
            "Skipping escalation check because the database is unavailable: %s", exc
        )
    except Exception:
        logger.exception("Unexpected failure while running escalation check")


def start_scheduler():
    scheduler.add_job(
        _job,
        trigger=IntervalTrigger(minutes=settings.ESCALATION_INTERVAL_MINUTES),
        id="escalation_check",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        f"Escalation scheduler started (every {settings.ESCALATION_INTERVAL_MINUTES} min)"
    )


def stop_scheduler():
    scheduler.shutdown(wait=False)
