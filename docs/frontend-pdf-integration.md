# Frontend PDF integration

The server-side PDF worker calls Tulun; the browser must never receive the caller
API key. Send selectable static text only and leave entered form-field values
unchanged. PDF extraction, placement and layout validation belong to the caller.

## Backend deployment

Publish the updated commit and create a new Tulun deployment. The default provider
call timeout is now 30 seconds, for Foundry as well as Gateway, despite the setting
name `AI_GATEWAY_TIMEOUT_SECONDS`. The manifest exposes it as an optional config
reference. If an existing reference supplies `15`, change it to `30`; existing
overrides take precedence over the code default. Do not put credentials in config.

The total translation deadline remains 60 seconds and Gunicorn timeout remains
75 seconds. Each segment normally makes two sequential model calls: translation
and post-editing. Both share the total deadline. No automatic model fallback or
backend provider retries are introduced. A longer timeout may reduce slow-call
failures but is not a guarantee of availability.

Keep one synchronous worker for the 512 MiB budget. Do not restore two workers
without measuring peak memory and increasing resources as necessary.

## Caller changes

- Set `TULUN_MAX_CONCURRENCY=1`. This is per worker process; multiple PDF jobs or
  worker replicas must share a deployment-wide concurrency limit of one for this
  Tulun instance. Independent per-job limits still overload the same backend.
- Keep the 120-second per-request timeout, but do not treat it as the whole-job
  deadline. Queue wait and proxy limits also affect requests. Do not probe health
  before every segment; health cannot establish provider availability.
- Submit exactly `text`, `source_language: "en"`, `target_language: "sm"` and
  `configuration_id: 1` for the currently configured Samoan system. Verify that
  configuration still matches the intended language. The default text limit is
  4,000 characters; do not truncate segments silently.
- Accept Tulun's non-empty string `translation` on a successful HTTP response.
  Do not treat an error body or unchanged development preview as a translation.
- Record job ID, segment index, character count, attempt number, HTTP status,
  elapsed time, and the JSON `error.code` and `error.request_id`. Record whether
  failure came from Tulun, a proxy or the caller timeout. Never log keys, extracted
  text, full provider responses or sensitive PDF content.
- Retry only transient failures: `FOUNDRY_TIMEOUT`, `FOUNDRY_UNAVAILABLE`,
  `FOUNDRY_RATE_LIMITED` (or their `GATEWAY_` equivalents), and bounded transport
  failures. Allow at most two retries per segment with jittered backoff, for
  example about 2 then 5 seconds; honor `Retry-After` and the whole-job deadline.
  A proxy 502/503/504 without Tulun JSON may be retried within the same budget.
  Do not blindly retry every 502/503: authentication and configuration errors
  require intervention. Do not retry validation or policy rejection errors.
- Retain successful results within the job and retry only failed segments.
  Deduplicate identical text within the same language/configuration/job. Avoid
  cross-job persistent caching without an approved retention policy. Tulun has no
  idempotency key: retries can cause duplicate model charges and database rows,
  especially after a caller timeout where the backend may still finish.
- Show progress by completed segments and a cancel option. Bound job duration and
  total attempts. Cancellation must stop new requests/retries; it does not
  guarantee cancellation of already-running model calls.
- Publish the translated PDF only after all required segments succeed and layout
  checks pass. Keep the original available on failure; do not label a partially
  translated or unchanged PDF as successfully translated. Explicit development
  preview must be visibly distinguished from real translation.

## Timing and verification

Four concurrent submissions do not yield four-way throughput with one synchronous
worker. For N unique segments, document time is approximately the sum of segment
processing times, plus extraction, PDF rewriting, retry delays and competing jobs.
Measure the actual PDF; short labels still incur two model calls. Do not concatenate
segments through the current plain-text endpoint and assume their location mapping
survives. Structured batching needs a separate validated API contract.

After deployment, run a representative PDF and record segment count, successes,
retry count and total duration. Verify effective memory usage and absence of new
kernel OOM kills, and check health/readiness during load. One worker can delay
health responses while translating; successful application health logs do not
measure time spent waiting before the worker begins handling the request.
