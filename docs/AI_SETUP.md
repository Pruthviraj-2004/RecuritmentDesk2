# AI extraction setup

**The application works without any AI provider.** You can sign in, connect accounts, sync, browse emails, create/edit/approve requirements manually, review duplicates and export. Without a provider, emails that look like job requirements are classified by rules and marked **Awaiting AI**; they are extracted automatically (or via *Retry failed / awaiting AI*) once a provider is configured. Live extraction itself requires a provider.

## Configure an OpenAI-compatible provider (server-side only)

```
AI_PROVIDER=openai_compatible
AI_API_KEY=...            # never sent to the browser
AI_BASE_URL=https://api.openai.com/v1     # any endpoint exposing POST /chat/completions
AI_MODEL=gpt-4o-mini
AI_TIMEOUT_SECONDS=60
AI_MAX_RETRIES=3
```
Restart the API and worker. **Settings → AI extraction** shows the provider/model/endpoint host (never the key) and has a *Run live health check* button.

## How extraction is kept safe

* Email text is wrapped in `<email>` tags and treated as data; the system prompt tells the model to ignore instructions inside it. The model has no tools and cannot send mail, change settings or write to the database; its output is parsed as JSON and validated against a Pydantic schema before anything is stored.
* Values must be supported by the source: recruiter/submission emails that do not literally appear in the email are discarded, skills not found in the text are removed (with a warning on the record), swapped experience/salary ranges are corrected, unsupported evidence snippets are dropped, and a completeness-based confidence score is stored.
* Missing information stays `null`; nothing is defaulted.
* Retries: network errors, timeouts, 429 and 5xx retry with backoff (bounded by `AI_MAX_RETRIES`, then Celery retries up to 4 times). **401/403 (bad key) and 400/404 (bad model/endpoint) are permanent**: the message is marked failed with a clear reason, a notification is created, and nothing retries forever.
* Every run is stored in `extraction_runs` (provider, model, prompt version, status, validated output, error code).

## Other places AI is used

The **Candidate AI Profile** agent uses the same provider settings (`AI_*`). It sends the text the user pastes or uploads (never a URL it fetched) in one request, only when the user clicks *Extract with AI*, and validates and grounds the answer before saving it. If the provider is not configured the tab says so and nothing is sent.

## Testing without a paid provider

`AI_PROVIDER=mock` exists for development and automated tests only (a deterministic heuristic provider). It is not for real use.

## Prompt/model changes

The prompt version (`v1`) is recorded on each run. Use *Reprocess* on an email to re-run extraction with the current configuration; reprocessing never duplicates requirements.
