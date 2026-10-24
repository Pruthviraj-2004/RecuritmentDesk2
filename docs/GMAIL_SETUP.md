# Gmail / Google OAuth setup

RecruitmentDesk uses Google's OAuth 2.0 consent screen. It never sees or stores a Gmail password.

## 1. Google Cloud project

1. <https://console.cloud.google.com> → create (or reuse) a project → **APIs & Services → Library → enable "Gmail API"**.
2. **OAuth consent screen** → External (or Internal for Google Workspace). Add the scopes `…/auth/gmail.readonly` and (optional) `…/auth/gmail.send`. While the app is in **Testing**, add every Gmail address you will connect under **Test users**.
3. **Credentials → Create credentials → OAuth client ID → Web application.** Add **Authorized redirect URIs** that match `GOOGLE_REDIRECT_URI` exactly:

| How you run it | Redirect URI to register |
|---|---|
| Local dev (`scripts\dev.ps1`) | `http://localhost:8000/api/v1/email-accounts/oauth/callback` |
| Docker Compose | `http://localhost:8080/api/v1/email-accounts/oauth/callback` |
| Production | `https://your-domain/api/v1/email-accounts/oauth/callback` |

4. Put the client ID/secret in `backend\.env` (and `.env` for Docker): `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`.

> If you reused a client from another app, **add the redirect URI above to that client** or Google will answer `redirect_uri_mismatch`.

## 2. Connecting accounts

Sign in → **Connected Accounts → Connect Gmail**. Tick *Allow sending exports* only if this account should be able to email Excel files. Repeat for each account (2–3 initially; more are supported). Each connection is independent and can be reauthorized, synced, or disconnected on its own.

* Testing-mode refresh tokens expire after **7 days**: the account then shows "Reauthorization needed" and sync pauses until you reauthorize (this is Google's behaviour, not a bug).
* If Google does not return a refresh token, remove the app at <https://myaccount.google.com/permissions> and connect again.

## 3. Verification and scope sensitivity

`gmail.readonly` and `gmail.send` are **restricted/sensitive scopes**. For personal use with your own accounts as Test users no verification is needed. To let other people connect their mailboxes in production you must complete Google's OAuth app verification (privacy policy, domain verification, demo video) and, for restricted scopes, a third-party security assessment (CASA). Plan for this before launch; do not describe an unverified app as Google-approved.

## 4. Sync behaviour

First sync reads the account's import window (default 30 days; 7–365 configurable) in pages with a durable checkpoint; later syncs use Gmail history IDs and fall back to a windowed reconcile if the cursor expires. Polling runs every `SYNC_INTERVAL_MINUTES` (Celery beat); a daily reconcile re-reads the last 3 days. Pub/Sub push (`GOOGLE_PUBSUB_TOPIC`) is reserved but not implemented: polling is the supported mechanism.
