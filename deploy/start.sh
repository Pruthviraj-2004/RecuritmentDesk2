#!/bin/sh
# Render entrypoint: migrate, start Celery worker + beat in the background (if Redis is configured), then run the API in the foreground.
set -e
alembic upgrade head
if [ -n "$REDIS_URL" ] && [ "$CELERY_EAGER" != "true" ]; then
  celery -A app.tasks.celery_app:celery_app worker --loglevel=INFO --concurrency=1 &
  celery -A app.tasks.celery_app:celery_app beat --loglevel=INFO --schedule=/tmp/celerybeat-schedule &
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-10000}" --proxy-headers --forwarded-allow-ips "*"
