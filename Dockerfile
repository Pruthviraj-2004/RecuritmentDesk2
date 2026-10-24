# Render / single-container image: builds the React app, then runs the API (serving it) plus the Celery worker and beat.
FROM node:22-alpine AS web
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
COPY backend/pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install . && rm -rf app
COPY backend/alembic.ini ./
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY --from=web /app/dist /srv/static
COPY deploy/start.sh /srv/start.sh
RUN useradd --system --uid 10001 --home /srv appuser && mkdir -p /data/storage && chown -R appuser /data /srv && chmod +x /srv/start.sh
USER appuser
ENV STORAGE_PATH=/data/storage STATIC_DIR=/srv/static
EXPOSE 10000
CMD ["/srv/start.sh"]
