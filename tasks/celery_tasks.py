"""
Celery Background Tasks
Periodic jobs and async tasks
"""
import structlog
from celery import Celery
from datetime import datetime, timedelta
from config.settings import settings

logger = structlog.get_logger(__name__)

# Initialize Celery
celery_app = Celery(
    "qbit_tasks",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend
)

# Celery configuration
celery_app.conf.update(
    task_serializer=settings.celery_task_serializer,
    result_serializer=settings.celery_result_serializer,
    accept_content=["json"],
    timezone=settings.celery_timezone,
    enable_utc=settings.celery_enable_utc,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max
    worker_prefetch_multiplier=1,
)


# ============================================================================
# PERIODIC TASKS
# ============================================================================
@celery_app.task(name="tasks.reset_monthly_credits")
def reset_monthly_credits():
    """
    Reset free tier credits monthly.
    Runs on the 1st of each month.
    """
    logger.info("monthly_credit_reset_started")
    
    # TODO: Implement MongoDB update to reset credits for free tier users
    # This would be:
    # db.users.update_many(
    #     {"tier": "free"},
    #     {"$set": {"credits": DEFAULT_USER_CREDITS}}
    # )
    
    logger.info("monthly_credit_reset_completed")
    return {"status": "success"}


@celery_app.task(name="tasks.cleanup_old_snapshots")
def cleanup_old_snapshots():
    """
    Clean up snapshots older than 30 days.
    Runs weekly.
    """
    logger.info("snapshot_cleanup_started")
    
    # TODO: Implement snapshot cleanup
    # Keep last 10 snapshots per project
    # Delete snapshots older than 30 days (except last 10)
    
    logger.info("snapshot_cleanup_completed")
    return {"status": "success"}


@celery_app.task(name="tasks.api_key_health_check")
def api_key_health_check():
    """
    Check health of API keys and log statistics.
    Runs every hour.
    """
    logger.info("api_key_health_check_started")
    
    from rotation.key_manager import groq_pool, cerebras_pool
    
    groq_health = groq_pool.get_health_status()
    cerebras_health = cerebras_pool.get_health_status()
    
    logger.info(
        "api_key_health_status",
        groq=groq_health,
        cerebras=cerebras_health
    )
    
    return {
        "groq": groq_health,
        "cerebras": cerebras_health
    }


# ============================================================================
# CELERY BEAT SCHEDULE (Periodic tasks)
# ============================================================================
celery_app.conf.beat_schedule = {
    "reset-credits-monthly": {
        "task": "tasks.reset_monthly_credits",
        "schedule": 2592000.0,  # 30 days in seconds
    },
    "cleanup-snapshots-weekly": {
        "task": "tasks.cleanup_old_snapshots",
        "schedule": 604800.0,  # 7 days in seconds
    },
    "api-key-health-hourly": {
        "task": "tasks.api_key_health_check",
        "schedule": 3600.0,  # 1 hour in seconds
    },
}
