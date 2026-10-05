# API and operations

## API contract

`GET /api/v1/health` returns `200 {"status":"ok"}`. It needs no authentication,
database query, external request, or tokens. It exposes no configuration values.

`GET /api/v1/ready` returns `200 {"status":"ready"}` only when database access,
schema/configuration and Gateway/client settings are ready. Otherwise it returns
controlled JSON with status 503. It does not validate a live Gateway, key lifecycle,
or model quality by calling an LLM; infrastructure health is independent of AI uptime.

`POST /api/v1/translate` requires `Content-Type: application/json` and
`Authorization: Bearer <TULUN_API_KEY>` (constant-time exact token comparison).
Session cookies are not API authentication. This runtime secret is separate from
Tulun's outgoing `AI_GATEWAY_API_KEY`; they must not be the same.

```json
{
  "text": "Treat the wound.",
  "source_language": "en",
  "target_language": "mi",
  "configuration_id": 1
}
```

All four fields are mandatory; unknown/duplicate fields are rejected. Text/languages
are nonempty strings; configuration ID is a positive integer, not a string/boolean.
The existing domain supports English source only. The target must exactly match
the explicitly selected singleton SystemConfiguration's code. `mi` is an example,
not a built-in/default Māori configuration. No hidden configuration creation occurs
on an API request. There are no configuration/glossary CRUD APIs.

```json
{
  "translation": "Whakaora te patunga.",
  "source_language": "en",
  "target_language": "mi",
  "configuration_id": 1,
  "translation_id": 42
}
```

The API uses TranslatorGateway within the existing TranslatorMixin hierarchy,
GlossaryEntry matching, CorpusEntry BM25 retrieval, existing prompt builder and
post-edit/correction logic. The adapter changes only first-pass transport and
post-edit completion transport. Both stages go through the Gateway. Example first
passes are reused in a request-local cache, not a plaintext on-disk JSON cache.
Translation plus glossary/memory associations persist atomically; `created_by` is
null because the sandbox shared API secret is not a Django user identity.

Errors have `{"error":{"code":"...","message":"...","request_id":"..."}}`.
Every response supplies `X-Request-ID` and `Cache-Control: no-store`. Safe incoming
IDs are 1–64 ASCII letters/digits/dot/underscore/hyphen; otherwise UUIDs are generated.

| HTTP status | Categories |
| --- | --- |
| 400 | INVALID_JSON, INVALID_REQUEST; includes malformed UTF-8, duplicates, missing/unknown fields/types. |
| 401 | UNAUTHORIZED; missing/invalid caller credential, WWW-Authenticate: Bearer. |
| 404 | CONFIGURATION_NOT_FOUND, NOT_FOUND; Admin/UI/legacy API absent in MSD mode. |
| 405 | METHOD_NOT_ALLOWED; Allow header provided for known routes. |
| 413 | REQUEST_TOO_LARGE, TEXT_TOO_LARGE. |
| 415 | UNSUPPORTED_MEDIA_TYPE. |
| 422 | UNSUPPORTED_LANGUAGE, TRANSLATION_CONTEXT_TOO_LARGE, GATEWAY_POLICY_REJECTED. |
| 429 | GATEWAY_RATE_LIMITED; generic Retry-After: 60, no Gateway response forwarded. |
| 500 | INTERNAL_ERROR; no stack trace, upstream body, credentials, or input echo. |
| 502 | GATEWAY_AUTHENTICATION_FAILED, GATEWAY_UNAVAILABLE, GATEWAY_INVALID_RESPONSE. |
| 503 | SERVICE_NOT_CONFIGURED, CONFIGURATION_NOT_SUPPORTED, DATABASE_UNAVAILABLE, NOT_READY. |
| 504 | GATEWAY_TIMEOUT; call timeout or total translation deadline. |

The compatible SDK sometimes normalizes a malformed HTTP 200 body into an upstream
exception: either safe 502 category is acceptable; raw details never reach callers.
Truncated/non-string/empty/refused outputs are not recorded as successful translations.
No automatic retries, streaming, or provider fallback. Retrying a successful request
is not idempotent: it can create another Translation and consume model tokens.
There is no local per-client rate limiter; the platform and Gateway must supply
admission/rate limits. Shared sandbox key is not production multi-tenant identity.

## Runtime environment

| Name | Requirement/default |
| --- | --- |
| DJANGO_SECRET_KEY | Required MSD secret; at least 50 characters with sufficient variation. |
| DATABASE_URL | Required MSD secret; dedicated PostgreSQL URL, never Main-Website's database. |
| TULUN_API_KEY | Required for translation/readiness; strong application caller secret, not a Gateway key. |
| AI_GATEWAY_API_KEY | Required for translation/readiness; app-specific Gateway-issued runtime secret. |
| AI_GATEWAY_BASE_URL | Required for translation/readiness; approved compatible HTTPS base ending in /v1; may include proxy prefix. No credentials/query/fragment. |
| AI_GATEWAY_MODELS | Required for translation/readiness; comma/space-separated approved Gateway aliases, without `openai/` provider prefix. Both DB model fields must match this allowlist. |
| DJANGO_ALLOWED_HOSTS | Comma/space-separated explicit hosts; default localhost and 127.0.0.1. Add platform hostname. Wildcard rejected in MSD. |
| TULUN_MODE | msd by default; development is explicit. Invalid values fail startup. |
| AI_GATEWAY_ALLOW_INSECURE_HTTP | false; explicit exception for isolated fake Gateway/local or approved private-network HTTP. Never enable for an Internet credential path. |
| TULUN_MAX_TEXT_LENGTH | 4000 characters; supported range 1–16000. |
| TULUN_MAX_BODY_BYTES | 32768 bytes; supported range 1024–131072. |
| AI_GATEWAY_TIMEOUT_SECONDS | 15 seconds per call; range 1–30, additionally capped by remaining total deadline. |
| TULUN_TRANSLATION_TIMEOUT_SECONDS | 60 seconds total model work deadline; range 5–90. CPU/DB work is finally bounded by Gunicorn/platform timeout. |
| AI_GATEWAY_MAX_OUTPUT_TOKENS | 2048 per model call; range 16–4096, must fit the Gateway credential allowance. |
| TULUN_MAX_PROMPT_CHARS | 24000 combined message characters; range 1000–64000. Includes DB glossary/examples/prompt. |
| TULUN_MAX_RETRIEVED_SENTENCES | 5; range 0–10. DB config retrieval count must be within this limit. |
| GUNICORN_WORKERS | 2 synchronous workers, hence at most 2 active translations/container; range 1–4. |
| GUNICORN_TIMEOUT_SECONDS | 75; range 10–120 and greater than total translation deadline plus 10 seconds. |
| DJANGO_DEBUG | Only effective in development; default false, never enabled in MSD. |
| TULUN_SQLITE_PATH | Development-only SQLite path; default repository db.sqlite3. Not accepted as MSD persistence. |
| TULUN_ENABLE_LEGACY_UI | Development-only false default; optional legacy UI/Admin opt-in. No subpath support promised. |
| DJANGO_CSRF_TRUSTED_ORIGINS | Development UI only when required; space-separated origins. API bearer auth does not depend on cookies/CSRF. |
| LOCAL_POSTGRES_PASSWORD | Local Compose only; generate a URL-safe password (for example hex). Not a platform variable. |

Missing Django secret/database prevents MSD startup. Missing client/Gateway settings
permit cheap liveness but fail readiness and translation closed. Configuration
validation rejects legacy Google/HF models and DSPy state in the API, even when
direct-provider environment keys exist. No direct credential variable is required.

Gunicorn binds 0.0.0.0:8000, uses 75-second graceful shutdown, recycles after 500
requests plus up to 50 jitter, and bounds request headers. Access logs are disabled
to avoid URLs/query/header/body leakage. The app logs JSON timestamp/request ID,
allowlisted route name, status, duration, and safe error category; no exception text,
body, prompt, translation, secret, host, or Authorization is logged. Sentry and
full-payload tracing are not enabled. LiteLLM uses its packaged local model-cost map
and no configured callbacks; SDK debug/HTTP logs are disabled. Do not enable SDK
callbacks or global tracing with full payloads in deployment.

## Local build and run

Copy `.env.example` to `.env`, fill runtime values locally, and restrict file
permissions (`chmod 600 .env`). Nothing real is included in the example.

```bash
docker build -t tulun-backend .
docker compose up -d db
docker compose run --rm api python manage.py migrate --noinput
docker compose run --rm api python manage.py configure_translation \
  --target-language-code mi --target-language-name 'Māori' \
  --translation-model APPROVED_ALIAS --post-editing-model APPROVED_ALIAS
docker compose up -d api
curl --fail http://127.0.0.1:8000/api/v1/health
```

Compose is local convenience only; its PostgreSQL named volume survives API/image
replacement. `docker compose down -v` deletes local data. MSD never executes it.
The application can start independently after explicit migrations. API-only mode
needs no static assets; the image retains source templates but does not expose or
serve UI/static routes. No collectstatic build command needs runtime secrets.

For protected requests, use a mode-600 temporary header file instead of putting
credentials in command arguments or terminal history:

```bash
headers=$(mktemp)
chmod 600 "$headers"
printf 'Authorization: Bearer %s\n' "$TULUN_API_KEY" > "$headers"
curl --fail-with-body --header @"$headers" --header 'Content-Type: application/json' \
  --data '{"text":"Treat the wound.","source_language":"en","target_language":"mi","configuration_id":1}' \
  http://127.0.0.1:8000/api/v1/translate
rm -f "$headers"
```

This displays translation output: use only approved synthetic data during smoke
testing. A real Gateway request consumes tokens; ordinary automated tests do not.

## Persistence and rollback

PostgreSQL is the supported MSD deployment database, externally supplied and backed
up by operations. API data is never authoritative in the disposable writable layer.
No SQLite production fallback. Development SQLite tests do not establish deployment
persistence. Existing SQLite users must perform an approved dump/load/data-validation
procedure; provisioning a new PostgreSQL DB does not automatically transfer data.
No schema migration added. Original schema allows one global configuration and
shared language-unscoped glossary/memory; do not repurpose it for multiple targets
or sensitive multi-tenant data without a separately designed migration.

Upstream intentionally persists source/final text in Translation and memory: the
no-payload policy here applies to operational logs, not removal of application data.
DB access/retention/classification must be approved; Gateway governance alone does
not replace database privacy controls. Request-local first-pass cache is ephemeral;
long-lived translation history/glossary/memory remain PostgreSQL data.

BM25 index is rebuilt from the corpus per request, as upstream. The adaptation fixes
the schema field mismatch and reloads committed index data, avoiding the old race.
Large corpora remain a CPU/RAM scaling risk: keep the sandbox corpus bounded and
use platform resource admission. No horizontal SQLite sharing or new background
queue/index service is introduced.

## Tests and supply chain

```bash
poetry run python manage.py test --settings=tulun.test_settings
TULUN_TEST_DATABASE_URL=postgresql://USER:PASSWORD@HOST/tulun_test \
  poetry run python manage.py test --settings=tulun.test_settings
TULUN_SMOKE_DATABASE_URL=postgresql://USER:PASSWORD@HOST/tulun_smoke \
  poetry run python scripts/runtime_smoke.py
python scripts/runtime_smoke.py --docker
```

Native smoke uses a dedicated disposable DB, migrates/configures it, starts actual
Gunicorn on 8000, calls a fake Gateway via real LiteLLM, restarts Gunicorn, and checks
stored translation. Container mode builds the real image, creates isolated local
PostgreSQL/fake-Gateway containers, runs explicit migrations, calls the authenticated
API, replaces the API container, verifies data, and removes its resources. It uses
random test secrets via protected env files, never live credentials. Do not run it
against production databases, an occupied local 8000, or production model endpoints.

```bash
pip install poetry==2.2.1 poetry-plugin-export==1.10.0 pip-audit==2.10.1
docker build -t tulun-verify .
bash scripts/supply-chain.sh tulun-verify
```

Run scanning under Python 3.12: exported requirements carry Python-version markers.
The scan must not be run under unsupported 3.13 and interpreted as meaningful zero
findings. Install organisation-approved Trivy first. Script exports locked main
dependencies, fails on known Python vulnerabilities, generates image CycloneDX SBOM,
and fails on HIGH/CRITICAL container findings. Results live under ignored artifacts/.
The spaCy model is a locked hashed direct URL and pip-audit reports it as unscannable;
review model provenance/hash and container SBOM, do not call this full supply-chain
assurance. Tool/action version updates and base-image digest pinning are operations
review gates. No vulnerability exceptions are silently added.

CI performs SQLite/PostgreSQL tests, real-image fake-Gateway smoke, scans, and SBOM.
The workflow has not been executed on GitHub by this local implementation. CPU
torch/HF/Google/DSPy are optional legacy dependencies, excluded from production
installation/image and main dependency scan. Python 3.12/Django 5.2 LTS and an updated
LiteLLM lock replace vulnerable inherited versions; exact versions live in poetry.lock.

## Upstream update process

```bash
git remote add upstream https://github.com/raphaelmerx/tulun.git
git fetch upstream
git log --oneline HEAD..upstream/main
```

Skip remote add if it already exists. Review upstream diffs/migrations/provider
defaults before integration. Integrate only after choosing an approved workflow;
never push to upstream. Preserve the fork-base hash/history and record each adopted
upstream hash and MSD changes. Re-run tests, image/persistence/Gateway checks, scans
and rollback review. Extra Git remotes are local config, not tracked repository files.

MSD changes: root JSON API/auth/error boundaries, metadata logs, request-scoped
configuration, Gateway adapter/deadlines/allowlist, database URL support, non-root
Gunicorn image, optional legacy dependency split, tests/scans/SBOM/operations docs.
Main-Website/deployment schema and live credentials remain out of scope.
