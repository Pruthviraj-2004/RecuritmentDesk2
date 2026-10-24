# Implementation plan & checklist

Status legend: ✅ implemented and covered by an automated test · 🟡 implemented, verified manually/partially · ⛔ not implemented / external dependency.

## Phases

> The Email Inbox screen/API was removed on request: only recruitment mail is searched for and stored.

| Phase | Scope | Status |
|---|---|---|
| A Foundation | config + startup validation, DB, Alembic migration, health endpoints | ✅ (migration upgrade/check/downgrade tested; applied to a real Neon PostgreSQL schema) |
| B Auth & accounts | argon2 login, server sessions, CSRF, roles, org scoping, rate limiting, bootstrap CLI | ✅ |
| C Gmail | OAuth+PKCE connect/reauthorize/disconnect, token encryption/refresh, initial + incremental + reconcile sync, checkpoints, cancel/retry | ✅ against fakes; 🟡 live Google not exercised (needs your consent + redirect URI) |
| D Extraction | MIME/HTML parsing, attachment safety, rule classifier, OpenAI-compatible provider, schema + evidence validation | ✅ (provider via mocked HTTP; live health check against the configured endpoint passed) |
| E Dedup & review | message + requirement dedup, versions, merge, duplicate review actions, audit | ✅ |
| F Frontend | all 10 screens against the real API, light/dark, responsive shell | ✅ (22 unit/component tests, 11 browser e2e tests) |
| G Export & delivery | openpyxl workbook, download, composer, Gmail send, idempotency, uncertainty handling | ✅ |
| H Hardening & docs | security review items, Docker/Compose, PowerShell scripts, docs | 🟡 Docker files validated with `docker compose config` only (daemon unavailable) |

## Requirements coverage notes

| Item | Status |
|---|---|
| 2–3+ Gmail accounts, independent connect/disconnect/reauth, default sender, per-account settings | ✅ |
| Import windows 7–365 days, resume after restart, bounded retries, history-ID incremental + fallback | ✅ |
| Classification into 8 categories | ✅ rule-based, overridden by AI classification when a provider is configured |
| PDF / DOCX / TXT attachments, quarantine of unsafe files | ✅ · **OCR for scanned PDFs: ⛔ not implemented** (reported as "no extractable text") |
| Cross-account duplicate emails and requirements, review UI, merge preserving sources | ✅ |
| Related-requirement links | ✅ (auto-recorded as `related` candidates; no dedicated relationship graph UI) |
| Body vs attachment conflict flagging | 🟡 compares reference ID and minimum experience only |
| Requirements table: filters, search, server pagination/sort, bulk actions | ✅ · **"Assign selected records": ⛔** (no assignment model; single-user scope) |
| Excel: formatting, column choice, summary/info sheets, formula-injection guard, no duplicate canonical rows, expiry | ✅ |
| Send via Gmail with confirmation, templates, status tracking | ✅ · "client-wise report" template is wording only (the workbook is the same export) |
| Dashboard KPIs + charts with date filter, table view, empty states | ✅ |
| Analytics incl. duplicate rate, extraction success, correction rate | ✅ (shows "—" when no data) |
| Settings (general, Gmail, AI status/threshold, dedup, notifications, security, health) | ✅ · only options that take effect are exposed; timeouts/retries/retention are server env settings |
| Candidate Profiles: single add, CSV/XLSX import with standard template + check step, duplicate handling, filters, bulk actions, notes, pipeline, matching, Excel export | ✅ |
| AI profile agent (paste/PDF/resume -> grounded structured profile, analytics, apply) | ✅ · **fetching a LinkedIn URL itself is deliberately not implemented** (LinkedIn forbids scraping); a licensed API/data provider would need to be added separately |
| Candidate resume file upload / parsing | ⛔ not implemented (a resume link field is stored) |
| Notifications | 🟡 in-app only (no email/push notifications) |
| Pub/Sub push notifications | ⛔ optional enhancement not implemented (polling + daily reconcile) |
| User/organization management UI | ⛔ data model and authorization are multi-user ready; there is no invite/role-management screen |
| Shared/S3 storage backend | ⛔ local storage only |
| Playwright e2e | ✅ 11 tests on an isolated server with fake Gmail/OAuth (never touches real accounts) |

## Test inventory

* `backend/tests` — 132 pytest tests (unit, API integration, workflow, migrations, provider).
* `frontend/src/test` — 35 vitest component/unit tests; `frontend/e2e` — 16 Playwright tests.
* `scripts\test.ps1 [-E2E]` runs everything.
