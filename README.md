# RecruitmentDesk

Recruitment email intelligence for consultants who receive job requirements in several Gmail accounts. It connects your Gmail accounts (Google OAuth), imports only recruitment-related emails (no mailbox mirror), extracts structured job requirements with AI, removes duplicates across accounts, lets you review/edit/approve, exports to Excel and can email the workbook through Gmail. A Candidate Profiles module keeps your talent database (add one by one or import CSV/Excel) and matches candidates to requirements.

* **Backend:** Python, FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, Celery + Redis, openpyxl
* **Frontend:** React, strict TypeScript, Vite, Tailwind, TanStack Query/Table, React Hook Form + Zod, Recharts
* **Works without AI:** everything except live extraction runs without an AI key (see [AI setup](docs/AI_SETUP.md)).

## Quick start (Windows PowerShell)

Prerequisites: Python 3.11+, Node 20+, and either Docker Desktop (recommended for PostgreSQL/Redis) or a PostgreSQL URL (e.g. Neon).

```powershell
scripts\setup.ps1                                     # venv, dependencies, generated keys -> backend\.env and .env
notepad backend\.env                                  # set DATABASE_URL, GOOGLE_CLIENT_ID/SECRET, optional AI_*
scripts\migrate.ps1                                   # create/upgrade the database schema
scripts\create-admin.ps1 -Email you@example.com       # first administrator (password is prompted)
scripts\dev.ps1                                       # API http://localhost:8000/api/docs , app http://localhost:5173
```

Docker Compose (everything incl. PostgreSQL, Redis, worker and scheduler, served on http://localhost:8080):

```powershell
scripts\setup.ps1; notepad .env
docker compose up -d --build
scripts\create-admin.ps1 -Email you@example.com -Docker
```

Connect Gmail from **Connected Accounts** after registering the OAuth redirect URI ([Gmail setup](docs/GMAIL_SETUP.md)).

## Tests

```powershell
scripts\test.ps1          # pytest + type-check + vitest
scripts\test.ps1 -E2E     # also Playwright browser tests (isolated server, fake Gmail/OAuth, uses installed Edge)
```

## What needs external credentials

| Capability | Needs | Without it |
|---|---|---|
| Connect Gmail, sync, send exports | Google OAuth client ID/secret + registered redirect URI (+ test users / verification) | accounts cannot be connected; existing data stays usable |
| Live AI extraction | `AI_PROVIDER=openai_compatible`, `AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL` | emails wait as **Awaiting AI**; manual entry, review, export all work |
| Background workers at scale | Redis (`REDIS_URL`) | tasks run inline in the API process (fine for development) |

## Candidate import templates

Ready-to-fill files are in [`templates/`](templates): `candidate-import-template.xlsx` (examples + Instructions sheet), `candidate-import-template-blank.xlsx` (headers only) and the same two as CSV. Name, email and phone are required for every candidate. `python -m app.cli seed-demo-candidates --yes` adds marked dummy candidates for demos and `purge-demo-candidates --yes` removes them.

## Documentation

[Architecture](docs/ARCHITECTURE.md) · [Database](docs/DATABASE.md) · [API](docs/API.md) · [Security](docs/SECURITY.md) · [Gmail setup](docs/GMAIL_SETUP.md) · [AI setup](docs/AI_SETUP.md) · [Deployment](docs/DEPLOYMENT.md) · [User guide](docs/USER_GUIDE.md) · [Implementation checklist & limitations](docs/IMPLEMENTATION_CHECKLIST.md)

## Repository layout

```
backend/    FastAPI app (app/), Alembic migrations, pytest suite (tests/), Dockerfile
frontend/   React SPA (src/), vitest tests, Playwright e2e (e2e/), nginx.conf, Dockerfile
docs/       architecture, security, setup and operations guides
scripts/    PowerShell helpers (setup, migrate, dev, test, backup/restore)
docker-compose.yml, .env.example
```

`backend/tests/e2e_server.py` is a **development-only** harness (fake Gmail/OAuth + a rule-based extraction stub on an isolated SQLite DB). It is never used by the normal application.
