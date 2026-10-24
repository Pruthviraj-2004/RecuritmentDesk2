# API

Versioned under `/api/v1`. Interactive OpenAPI docs (development only): `http://localhost:8000/api/docs`; schema at `/api/openapi.json`. Frontend types live in `frontend/src/types/api.ts` and mirror `backend/app/schemas/api.py`.

**Auth model:** `POST /auth/login` sets an HttpOnly, SameSite session cookie and returns a `csrf_token`; every non-GET request must send it as `X-CSRF-Token`. Roles: `viewer` (read) < `member` (edit, sync, export, send) < `admin` (accounts, settings) < `owner`.

**Errors** always look like `{"error": {"code", "message", "details", "request_id"}}` (401 unauthenticated, 403 forbidden/csrf_failed, 404, 409 conflict, 422 validation, 429 rate_limited).
**Pagination:** `?page=&page_size=` → `{items, total, page, page_size}`.

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/login` · `POST /auth/logout` · `GET /auth/me` · `POST /auth/change-password` · `GET /auth/sessions` · `POST /auth/sessions/{id}/revoke` (no refresh endpoint: sessions are server-side with a fixed TTL) |
| Gmail accounts | `GET /email-accounts` · `POST /email-accounts/connect` (returns Google's authorization URL) · `GET /email-accounts/oauth/callback` · `GET/PATCH/DELETE /email-accounts/{id}` · `POST /email-accounts/{id}/reauthorize` · `POST /email-accounts/{id}/sync` · `POST /email-accounts/sync-all` |
| Processing issues | `GET /jobs/issues` (failed / awaiting-AI messages, metadata only) · `POST /emails/retry-failed` (there is intentionally no inbox/list-emails API) |
| Requirements | `GET/POST /requirements` · `GET/PATCH/DELETE /requirements/{id}` (DELETE archives) · `POST /requirements/{id}/approve|reject|archive|restore` · `POST /requirements/bulk` · `GET /requirements/{id}/sources|versions|similar` |
| Candidates | `GET/POST /candidates` (name, email, phone required on create) · `GET/PATCH/DELETE /candidates/{id}` (DELETE archives) · `POST /candidates/{id}/restore` · `GET /candidates/stats` · `POST /candidates/bulk` · `POST /candidates/export` (.xlsx) · `GET /candidates/import/template?format=csv\|xlsx` · `POST /candidates/import/preview` (dry run) · `POST /candidates/import` (multipart `file`, `on_duplicate=skip\|update`) · `GET /candidates/imports` · `GET/POST /candidates/{id}/notes` · `GET/POST /candidates/{id}/submissions` · `PATCH/DELETE /candidates/submissions/{id}` · `GET /candidates/{id}/matching-requirements` · `GET /requirements/{id}/matching-candidates` · `GET /requirements/{id}/submissions` |
| Candidate AI profile | `POST /candidates/{id}/ai-profile` (multipart: `text` or `file`, `source`; runs the agent) · `GET /candidates/{id}/ai-profile` (latest) · `GET /candidates/{id}/ai-profiles` · `GET /candidates/{id}/ai-profiles/{pid}` · `POST /candidates/{id}/ai-profiles/{pid}/apply` (`fields`) · `DELETE /candidates/{id}/ai-profiles/{pid}` |
| Duplicates | `GET /duplicates` · `GET /duplicates/{id}` · `POST /duplicates/{id}/merge|keep-both|mark-related|dismiss|reopen` |
| Exports & delivery | `POST/GET /exports` · `GET /exports/{id}` · `GET /exports/{id}/download` · `GET /exports/columns` · `POST /exports/{id}/send` (requires `confirm: true`; optional `Idempotency-Key` header) · `GET /deliveries` · `POST /deliveries/{id}/retry` |
| Operations | `GET /jobs` · `GET /jobs/summary` · `GET /jobs/{id}` · `POST /jobs/{id}/cancel|retry` · `GET /audit-logs` · `GET /notifications` · `POST /notifications/read-all` |
| Analytics | `GET /analytics/overview` · `GET /analytics/recruitment` (`date_from`, `date_to`) |
| Settings | `GET/PUT /settings/{general|gmail|ai|dedup|notifications}` · `GET /settings-meta/ai?check=true` |
| Health | `GET /health` (public liveness: status only) · `GET /health/details` (authenticated) |

Requirement list filters: `q, date_from, date_to, account_id, client, job_title, skill, exp_min, exp_max, location, work_mode, salary_min, salary_max, recruiter, review_status, lifecycle_status, source_type, duplicate_status, sort, direction`.

Deviations from the original target contract: reauthorize/bulk/reopen/retry-failed/settings endpoints were added; `POST /auth/refresh` was intentionally not implemented; `DELETE /requirements/{id}` archives instead of destroying data.
