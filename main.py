"""
QuantLive Signal Platform â Entry Point
-----------------------------------------
Starts the APScheduler cron that fires the pipeline
at :00 and :30 of every hour.

Also initialises the database on startup.
"""
import logging
import signal
import sys
import time
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

import config
from db.connection import init_db
from pipeline import run_pipeline
from alerts.telegram import send_heartbeat

# âââ Logging Setup âââââââââââââââââââââââââââââââââââââââââââââ
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("quantlive.main")


# âââ Scheduler Job âââââââââââââââââââââââââââââââââââââââââââââ

def scheduled_pipeline():
    """Wrapper called by APScheduler."""
    try:
        run_pipeline(silent_no_trade=False)
    except Exception as exc:
        log.error(f"Unhandled error in pipeline: {exc}", exc_info=True)


def hourly_heartbeat():
    """Send hourly heartbeat to confirm bot is alive."""
    send_heartbeat()


# âââ Startup âââââââââââââââââââââââââââââââââââââââââââââââââââ

def startup():
    log.info("=" * 60)
    log.info("  QuantLive Signal Platform â Starting Up")
    log.info(f"  Symbol:  {config.SYMBOL}")
    log.info(f"  Account: ${config.ACCOUNT_SIZE:,.0f}")
    log.info(f"  Schedule: :00 and :30 past every hour (UTC)")
    log.info("=" * 60)

    # Initialise database tables
    try:
        init_db()
        log.info("Database ready.")
    except Exception as exc:
        log.error(f"Database init failed: {exc}")
        log.warning("Running without database persistence.")

    # Send startup heartbeat
    send_heartbeat()

    # Run one pipeline cycle immediately on startup
    log.info("Running initial pipeline cycle on startupâ¦")
    try:
        run_pipeline(silent_no_trade=False)
    except Exception as exc:
        log.error(f"Startup pipeline run failed: {exc}", exc_info=True)


# âââ Main ââââââââââââââââââââââââââââââââââââââââââââââââââââââ

def main():
    startup()

    scheduler = BlockingScheduler(timezone="UTC")

    # Fire at :00 and :30 of every hour
    scheduler.add_job(
        scheduled_pipeline,
        trigger=CronTrigger(minute="0,30", timezone="UTC"),
        id="pipeline_job",
        name="ICT Signal Pipeline",
        max_instances=1,
        coalesce=True,
    )

    # Heartbeat every 30 min (:00 and :30)
    scheduler.add_job(
        hourly_heartbeat,
        trigger=CronTrigger(minute="0,30", timezone="UTC"),
        id="heartbeat_job",
        name="Telegram Heartbeat",
        max_instances=1,
    )

    # Graceful shutdown on SIGTERM (Railway sends this on deploy/stop)
    def _shutdown(signum, frame):
        log.info("Received shutdown signal. Stopping schedulerâ¦")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    log.info("Scheduler started. Waiting for next :00 or :30â¦")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
