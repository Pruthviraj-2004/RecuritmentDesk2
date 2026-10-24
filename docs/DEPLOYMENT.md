# Deployment

## Local with Docker Compose (Windows PowerShell)

Prerequisites: Docker Desktop (running), PowerShell. Python/Node are only needed for local development.

```powershell
scripts\setup.ps1                       # creates .env (+ backend\.env) with generated SECRET_KEY / ENCRYPTION_KEY / POSTGRES_PASSWORD
notepad .env                            # add GOOGLE_CLIENT_ID/SECRET (+ AI_*). Keep APP_ENV=development for plain-http localhost
docker compose up -d --build            # db, redis, migrate (one-shot), api, worker, beat, frontend
scripts\create-admin.ps1 -Email you@example.com -Docker      # prompts for a password
start http://localhost:8080
```
Stop / restart / logs: `docker compose stop` · `docker compose up -d` · `docker compose logs -f api worker`. Wipe everything (including data): `docker compose down -v`.
Backups: `scripts\backup-db.ps1`, `scripts\restore-db.ps1 -File backups\<file>.dump`.

> Docker was not available in the environment where this project was built, so the Dockerfiles and `docker-compose.yml` were validated with `docker compose config` but **not run**. Expect to fix small environment-specific issues on first start.

## Production path

| Concern | Recommendation |
|---|---|
| Database | Managed PostgreSQL 14+ (Neon, RDS, Cloud SQL). Set `DATABASE_URL` (`postgresql+psycopg://…`). Use a dedicated database or `DATABASE_SCHEMA`. Enable automated backups + PITR. |
| Redis | Managed Redis (e.g. Upstash/ElastiCache). `REDIS_URL=rediss://…`. It is only a broker; losing it loses queued (not persisted) tasks, which `process_pending` / `resume_stuck` re-create from database state. |
| API + workers | Same backend image, three commands: API (`uvicorn`), worker (`celery … worker`), beat (`celery … beat`, **exactly one replica**). Scale workers horizontally; tasks are idempotent. |
| Frontend | The nginx image (serves the SPA, proxies `/api` → API) or any static host **with `/api` routed to the API on the same origin** (cookies and CSRF assume same-origin). |
| TLS | Terminate HTTPS at your load balancer / ingress. Set `APP_ENV=production`, `SESSION_COOKIE_SECURE=true`, `FRONTEND_URL=https://…`. Production startup fails if these are unsafe. |
| Secrets | Secret manager / platform secrets for `SECRET_KEY`, `ENCRYPTION_KEY`, `GOOGLE_CLIENT_SECRET`, `AI_API_KEY`, DB/Redis URLs. Back up `ENCRYPTION_KEY` separately: without it stored Gmail tokens are unreadable (accounts need reauthorization). |
| Migrations | Run `alembic upgrade head` as a release step before starting new API/worker versions (compose does this with the `migrate` service). Migrations are forward-only in normal operation; take a backup before any downgrade. |
| Files | `STORAGE_PATH` must be a persistent volume shared by API and workers. Only extracted text and exports are stored. For multiple nodes implement/attach shared storage (S3 backend is not implemented). |
| OAuth | Register `https://your-domain/api/v1/email-accounts/oauth/callback`, publish/verify the consent screen (see GMAIL_SETUP.md). |
| AI | Set `AI_*`; check **Settings → System health**. |
| Observability | Logs are JSON on stdout (request id, job id). `GET /api/v1/health` is the liveness/readiness probe (503 if the database is down). Authenticated `/health/details` reports Redis, workers, AI and Gmail configuration. |
| Retention / recovery | `cleanup` runs every 6 h. Restore = restore the DB dump, restore `ENCRYPTION_KEY`, run migrations, run a full re-import per account (idempotent). |

Do not deploy to live infrastructure without your own credentials and approval; nothing in this repository does so.
