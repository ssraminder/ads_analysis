web: uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
worker: celery -A src.tasks.celery_app worker --loglevel=info --concurrency=2
beat: celery -A src.tasks.celery_app beat --loglevel=info
