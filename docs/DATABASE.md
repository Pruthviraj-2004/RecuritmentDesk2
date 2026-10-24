# Database

PostgreSQL 16 in production (tested against Neon PostgreSQL 18), SQLAlchemy 2 models, Alembic migrations (`backend/alembic/versions`). SQLite is used **only** by the automated tests/e2e server. UUID primary keys everywhere, timezone-aware UTC timestamps, foreign keys with explicit `ON DELETE`, and uniqueness enforced in the database.

Tables are never created by the application at runtime; run `alembic upgrade head` (the compose `migrate` service does this).

## Tables

| Table | Purpose / key constraints |
|---|---|
| `users`, `organizations`, `organization_memberships` | multi-user/multi-org ready; membership role: owner/admin/member/viewer; unique `(organization_id, user_id)` |
| `user_sessions` | server-side sessions (SHA-256 of cookie token, CSRF token, expiry, revocation) |
| `oauth_states` | single-use OAuth `state` hash + PKCE verifier bound to the initiating user, 10-minute expiry |
| `email_accounts` | Gmail connection; encrypted access/refresh tokens; scopes; status; unique `(organization_id, provider, email_address)` and `(provider, provider_account_id, organization_id)` |
| `email_sync_states` | one per account: `gmail_history_id`, last success, status, error |
| `email_messages` | unique `(email_account_id, gmail_message_id)`; `normalized_content_hash` for cross-account duplicates; `duplicate_of_message_id`; classification, status, truncated body (purged after retention) |
| `email_attachments` | filename, type, size, content hash, extraction status, reference to **extracted text** (raw files only if enabled) |
| `job_requirements` | canonical requirement (all fields from the spec) + normalized client/title/location, `canonical_fingerprint`, `review_status`, `lifecycle_status`, `merged_into_id`, `validation_warnings`, `version_number` |
| `requirement_skills` | normalized child table (required/preferred), unique per requirement; indexed for search/analytics |
| `requirement_sources` | links requirement ↔ email (unique `(requirement, message, source_type)`) with evidence metadata |
| `requirement_versions` | before/after of every change, `change_source` (extraction, manual_edit, dedup_enrichment, merge, status) |
| `duplicate_candidates` | unique ordered pair `(requirement_id_a, requirement_id_b)` (a < b), score, reasons, conflicting fields, review status |
| `extraction_runs` | provider/model/prompt version, status, validated output, error code |
| `processing_jobs` | sync/export jobs: status, progress, attempts, `checkpoint`, `stats`, error |
| `export_jobs`, `email_deliveries` | export options/filters/selection, private file reference, expiry; delivery status, tracking `Message-ID`, `idempotency_key` (unique per org) |
| `candidates` | talent profile; **name, email, phone NOT NULL** (everything else nullable); unique `(organization_id, email_normalized)`; phone matched on `phone_normalized` (last 10 digits); status, rating, tags, archive flag |
| `candidate_skills`, `candidate_notes`, `candidate_submissions`, `candidate_imports` | normalized skills; notes + status/pipeline timeline; pipeline entry per `(candidate, requirement)` with stage; import history with capped error report |
| `candidate_ai_profiles` | one row per AI profile run: validated result (profile + calculated analytics + warnings), model, prompt version, applied fields; input stored only as a SHA-256 |
| `audit_logs`, `notifications`, `app_settings` | append-only audit trail; in-app notifications; per-org settings sections |

PostgreSQL-only extras in migration `0001`: `pg_trgm` extension and trigram GIN indexes on requirement title/client/location. Search itself is portable `ILIKE` with escaped wildcards.

## Shared database / schema isolation

Set `DATABASE_SCHEMA=recruitmentdesk` to keep all tables in their own schema (used when RecruitmentDesk shares a Neon database with another application). It uses SQLAlchemy `schema_translate_map`, which also works through pooled (PgBouncer) endpoints, and Alembic creates the schema and keeps its version table there.

## Migrations and rollback

```powershell
scripts\migrate.ps1              # alembic upgrade head
scripts\migrate.ps1 -Downgrade   # one revision back (alembic downgrade -1)
```
The test suite upgrades a fresh database, runs `alembic check` (models must equal migrations), downgrades to base and upgrades again. Before downgrading production, take a dump with `scripts\backup-db.ps1`.

## Retention

`cleanup` (every 6 h): marks expired exports and deletes their files (`EXPORT_RETENTION_DAYS`), purges email bodies older than `EMAIL_BODY_RETENTION_DAYS` (they are re-fetched from Gmail only if a message is reprocessed). Audit logs and requirement history are kept.
