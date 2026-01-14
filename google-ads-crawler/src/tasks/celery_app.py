"""Celery application configuration."""

from celery import Celery
from celery.schedules import crontab

from src.config import settings

# Create Celery app
celery_app = Celery(
    "google_ads_crawler",
    broker=settings.celery_broker,
    backend=settings.celery_backend,
    include=[
        "src.tasks.keyword_tasks",
        "src.tasks.domain_tasks",
    ],
)

# Configure Celery
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Task execution
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=600,  # 10 minutes max
    task_soft_time_limit=540,  # Soft limit at 9 minutes

    # Worker settings
    worker_prefetch_multiplier=1,  # Don't prefetch tasks (important for long-running tasks)
    worker_concurrency=settings.MAX_CONCURRENT_SCRAPERS,

    # Result backend
    result_expires=86400,  # Results expire after 24 hours

    # Rate limiting (per worker)
    task_default_rate_limit="10/m",  # 10 tasks per minute max

    # Retry settings
    task_default_retry_delay=60,  # 1 minute retry delay
    task_max_retries=3,

    # Beat scheduler
    beat_schedule={
        # Refresh keywords every hour
        "schedule-keyword-refresh": {
            "task": "src.tasks.keyword_tasks.schedule_keyword_refresh",
            "schedule": crontab(minute=0),  # Every hour at :00
        },
        # Update advertiser stats every 6 hours
        "update-advertiser-stats": {
            "task": "src.tasks.domain_tasks.update_all_advertiser_stats",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        # Clean up old jobs daily
        "cleanup-old-jobs": {
            "task": "src.tasks.keyword_tasks.cleanup_old_jobs",
            "schedule": crontab(minute=0, hour=3),  # 3 AM daily
        },
    },
)


# Task routing
celery_app.conf.task_routes = {
    "src.tasks.keyword_tasks.*": {"queue": "scraping"},
    "src.tasks.domain_tasks.*": {"queue": "expansion"},
}

# Priority queues
celery_app.conf.task_queues = {
    "scraping": {
        "exchange": "scraping",
        "routing_key": "scraping",
    },
    "expansion": {
        "exchange": "expansion",
        "routing_key": "expansion",
    },
}
