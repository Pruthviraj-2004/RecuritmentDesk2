# Security

| Concern | What is implemented | Where |
|---|---|---|
| Authentication | Argon2id password hashes; 8+ char policy (plus mixed case and a digit); generic login errors (no user enumeration); failed-login lockout (8 / 10 min per account, 30 per IP) counting **failures only**; no hardcoded passwords | `core/security.py`, `endpoints/auth.py` |
| Sessions | server-side sessions, only a SHA-256 of the cookie token stored; HttpOnly + SameSite cookie, `Secure` enforced in production; revocation, "revoke other sessions" on password change | `models/auth.py`, `api/deps.py` |
| CSRF | per-session token required in `X-CSRF-Token` on every non-GET request; held in memory by the SPA (never localStorage) | `api/deps.py`, `frontend/src/lib/api.ts` |
| CORS | explicit origins only; `*` is rejected at startup | `core/config.py`, `main.py` |
| Authorization | role checks on every route; every query filtered by `organization_id`; cross-org access returns 404 (tested) | `api/deps.py`, tests |
| Gmail tokens | encrypted at rest with Fernet (`ENCRYPTION_KEY`); never returned by the API, never logged, never in the browser; disconnect revokes at Google and deletes stored credentials | `integrations`, `services/gmail/accounts.py` |
| OAuth | random single-use `state` bound to the user, 10-minute expiry, PKCE (S256), fixed return path (no open redirect), exact redirect URI | `services/gmail/accounts.py` |
| Least privilege | `gmail.readonly` for sync; `gmail.send` only if the user ticks "Allow sending exports" and can be granted later | `integrations/gmail_client.py` |
| Untrusted email content | HTML → text with scripts/styles/forms removed; text is rendered with React (no `dangerouslySetInnerHTML`); the AI prompt delimits content and ignores embedded instructions; model output is schema-validated and the model has **no tools or authority** (cannot send mail or change data); invented emails are dropped by evidence validation | `normalization`, `extraction` |
| Attachments | type sniffed from bytes (not name/MIME); size limits; executables, macro documents (`vbaProject.bin`), encrypted PDFs and zip bombs (entry count, ratio, expanded size, path traversal) are quarantined/unsupported; nothing is executed; failures never fail a sync | `services/gmail/attachments.py` |
| SSRF | the server never fetches URLs found in emails or attachments; the only outbound hosts are Google and `AI_BASE_URL` (must be http/https) | — |
| Exports | formula-injection guard on every untrusted cell; sheet/file name sanitization; private storage (never served statically); authenticated download with org check, `Cache-Control: no-store`, expiry + cleanup | `services/exports` |
| Sending email | explicit `confirm: true`; address validation incl. header-injection characters; attachment size limit; idempotency key; never automatic; ambiguous outcomes are `uncertain`, never auto-resent | `services/delivery` |
| SQL injection | SQLAlchemy parameterized queries; `LIKE` wildcards escaped | `services/requirements/query.py` |
| Logging | structured JSON in production, request/job IDs; tokens, keys, passwords redacted by pattern; email bodies never logged | `core/logging.py` |
| Headers | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, HSTS (production); strict CSP in the nginx image | `main.py`, `frontend/nginx.conf` |
| Startup validation | production refuses to start with a weak/missing `SECRET_KEY`/`ENCRYPTION_KEY` or insecure cookies; messages never print secret values | `core/config.py` |
| Audit | login/logout/failed login, account connect/disconnect, edits, approvals, merges, exports, downloads, sends, settings | `services/audit` |

## Candidate AI profiles

* Never fetches LinkedIn (or any) URLs: LinkedIn forbids automated access and a server-side fetch would also be an SSRF risk. The agent only reads text the user pastes or uploads (files go through the same byte-sniffing, size and macro/zip-bomb checks as email attachments).
* The profile text is untrusted: it is delimited in the prompt, instructions inside it are ignored, the model has no tools, and its output is schema-validated and grounded against the source text before anything is saved.
* The prompt forbids inferring protected characteristics; "things to verify" are neutral and computed from dates. Source text is not stored (only a SHA-256 and the extracted result). Running it is limited to members and 15 runs per user per hour.

## Known limitations / operator responsibilities

* The login rate limiter is **in-process**: with several API replicas also rate-limit at the reverse proxy.
* Local file storage is single-node; use a shared volume (or implement another storage backend) for multiple replicas.
* There is no TOTP/SSO. Add them before opening the app to more users.
* Google classifies Gmail scopes as **restricted**. A production app used by users outside your own Google Workspace/test-user list requires Google's OAuth verification and, for restricted scopes, a security assessment. Until then the consent screen shows "unverified app" and tokens for apps in *Testing* status expire after 7 days. This software does not represent itself as verified.
* Email bodies are retained (truncated) for `EMAIL_BODY_RETENTION_DAYS`; unrelated mail is purged right after classification.
* Run `pip-audit` / `npm audit` and scan the images (e.g. Trivy) in your CI; they are not run automatically here.
