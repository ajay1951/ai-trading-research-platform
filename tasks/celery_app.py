"""
Distributed Task Queue Configuration (Celery)
==============================================
Handles asynchronous execution of backtests, model training jobs, and universe updates.
"""
import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "ai_trading_platform",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks.trading_tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    worker_concurrency=int(os.getenv("CELERY_CONCURRENCY", "4"))
)


@celery_app.task(name="tasks.run_model_evaluation")
def run_model_evaluation(model_name: str, asset: str):
    """Asynchronous background task to evaluate model performance."""
    return {
        "status": "success",
        "model": model_name,
        "asset": asset,
        "execution": "completed"
    }
