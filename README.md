# Tulun — MSD backend fork

This MSD-controlled fork adapts Tulun's existing English-to-configured-language
translation and post-editing pipeline into a bounded, authenticated Django API.
Both model stages use the explicitly selected provider: the Governed AI Gateway
by default, or direct Azure AI Foundry when `AI_PROVIDER=foundry`. Foundry support
uses its OpenAI-compatible `/openai/v1` Chat Completions or Responses endpoint.
The deployed configuration uses the Foundry Responses endpoint and `gpt-6-luna`
for English-to-Samoan translation. There is no automatic provider fallback, and
Google/Gemini/legacy providers remain disabled in MSD mode.

For the temporary Foundry setup, see [Foundry deployment](docs/foundry-deployment.md).
The actual Foundry key remains a protected runtime secret, never a manifest value.

Public upstream: `https://github.com/raphaelmerx/tulun` (MIT).
Fork base: `e81f7a7291b3d7636818be7c7c35f50811dd0747` (`Update README.md`).
MSD remote: `https://github.com/msd-emerging-tech/tulun.git` (`tulun-origin`).
The `upstream` Git remote is preserved locally; cloning does not preserve extra
remotes, so add it explicitly when needed.

## Deployed instance

Main-Website's **Translation Backend** prototype deployed successfully on
**14 October 2026**. GitHub Actions run **#301** (`38495869532`) completed
successfully; its logs confirm vulnerability admission, protected-secret resolution,
database migrations, startup, health, readiness, Caddy activation and active-release
reporting. This is a deployment record, not a guarantee of ongoing availability.

| Item | Deployment value |
| --- | --- |
| Platform | Main-Website version-2 Custom Docker, registered through root `prototype.yml` |
| Prototype slug / service | `translation-backend` / `tulun-api` |
| Prototype ID | `cmuvwmtqd002b103fpu0jcxwy` |
| Successful deployment ID | `cmv7fkhby00dq11oncwbig4w5` |
| Application commit | `6c5facc5e7b92657dd367ef3cadadfc3c666a8c1` |
| Image repository | `emergingtechmain.azurecr.io/prototypes/translation-backend/tulun-api` |
| Image digest | `sha256:6a7abfb26bfd84740e48ee1a728ea0288d49d1c75388d0618809d8c6d0304e89` |
| Runtime | Python 3.12, Django, Gunicorn; internal port `8000`; UID/GID `10001` |
| Database | Platform-managed PostgreSQL, outside the API container |
| Translation | English (`en`) → Samoan (`sm`), configuration ID `1` |
| AI provider / model | Direct Azure AI Foundry (`AI_PROVIDER=foundry`) / `gpt-6-luna` for both stages |
| Foundry endpoint | `https://claude-sonnet-resource.services.ai.azure.com/openai/v1/responses` |
| API style | `AZURE_FOUNDRY_API_STYLE=responses` |

Direct Foundry is the temporary alternative while Governed AI Gateway key
provisioning is unavailable. **It bypasses the Gateway's inspection, credential
registry, audit and per-client governance controls.** Deployment admission and
application controls still apply; do not treat this as a Gateway-governed deployment.

Health and readiness passed on the deployment's private network. Readiness checks
database/configuration and credential presence without calling Foundry. A successful
live translation, actual provider-key validity, model access and public HTTPS
reachability have not yet been verified in this deployment record.

### Access and translation requests

The platform publishes these routes under the registered slug and strips the
prefix before forwarding to Django:

| Method | Public route | Authentication |
| --- | --- | --- |
| `GET` | `/translation-backend/api/v1/health` | None; no database or model call |
| `GET` | `/translation-backend/api/v1/ready` | None; database/configuration readiness |
| `POST` | `/translation-backend/api/v1/translate` | `Authorization: Bearer <TULUN_API_KEY>` |

Use the public origin shown by Main-Website for this prototype; the VM SSH address
is not necessarily the public hostname. A request for the deployed Samoan
configuration is:

```http
POST /translation-backend/api/v1/translate
Content-Type: application/json
Authorization: Bearer <TULUN_API_KEY>

{
  "text": "Hello, how are you?",
  "source_language": "en",
  "target_language": "sm",
  "configuration_id": 1
}
```

Replace the credential placeholder only in your approved API client, not in this
file or a shared log. Successful responses include `translation`, language codes,
`configuration_id` and `translation_id`. Translation requests consume model tokens
and persist source, initial and final translation text in PostgreSQL. Do not submit
sensitive data without the required approval; retries can create duplicate records.

### Configuration and secrets

In Main-Website → **Services & Configuration** for `tulun-api`:

- Set `AI_PROVIDER=foundry`, `AZURE_FOUNDRY_API_STYLE=responses`, the endpoint above
  and `AZURE_FOUNDRY_MODELS=gpt-6-luna`.
- Set `DJANGO_ALLOWED_HOSTS` to `localhost,127.0.0.1,tulun-api` plus the actual public
  hostname. Entries are hostnames only: no scheme, port, `/translation-backend`
  path or wildcard. `tulun-api` is required for private health/readiness probes.
- Use protected references for `DJANGO_SECRET_KEY`, `TULUN_API_KEY` and
  `AZURE_FOUNDRY_API_KEY`; the caller key must differ from the provider key.
- Leave `DATABASE_URL` platform managed and unused `AI_GATEWAY_*` bindings empty.

Keep the three secret configuration layers separate:

1. **VM secret values:** the installed renderer
   `/opt/prototypes/scripts/render-prototype-secret` references
   `/opt/prototypes/config/prototype-secrets/values.json`. The store is a JSON object
   mapping reference names to actual string values; preserve existing entries and
   runner-only permissions. Never paste its contents into logs, chat or Git.
2. **Main-Website approval:** `PROTOTYPE_CUSTOM_DOCKER_SECRET_REFS` is a names-only
   environment setting mapping prototype IDs to approved references. It is **not**
   an entry in `values.json` and does not store or generate keys. Merge approvals
   with other prototypes rather than replacing the entire allowlist. For this setup:

   ```dotenv
   PROTOTYPE_CUSTOM_DOCKER_SECRET_REFS={"cmuvwmtqd002b103fpu0jcxwy":["AZURE_FOUNDRY_API_KEY","approved-tulun-caller","approved-tulun-django"]}
   ```

3. **Service bindings:** save those exact reference names in the matching secret
   fields in Services & Configuration. Local `.env` files do not configure the
   deployed service. Verify names against the active backend before changing them.

Migrations alone do not create the translation configuration. Configuration ID `1`
was explicitly provisioned for Samoan with both model fields set to `gpt-6-luna`.
For a new empty database, run the following only through the approved runtime with
its protected environment and database access:

```bash
python manage.py configure_translation \
  --target-language-code sm --target-language-name Samoan \
  --translation-model gpt-6-luna \
  --post-editing-model gpt-6-luna
```

This command writes the singleton configuration, resets its post-edit prompt and
clears legacy DSPy state; it makes no model calls. Do not rerun it casually against
existing configuration, and use the returned ID rather than assuming `1` on a new DB.

### Redeployment and troubleshooting

Save service configuration changes, then create a **new Tulun deployment**. Existing
deployment snapshots and generated environment files are immutable; inspecting an
old failed deployment's file will still show its old values. Publish application
changes first and deploy the new exact commit; rerunning an old snapshot will not
pick them up. Service configuration changes do not require recreating Main-Website.

If Main-Website's own loaded environment is changed, recreate only that service
using the shared stack's normal procedure, restore any private network attachment
and verify health. A simple restart does not reload Compose environment settings;
never run `down` or `--remove-orphans` against the shared stack. See
[Foundry deployment](docs/foundry-deployment.md) for provider configuration.

| Failing stage | Checks that resolved deployment blockers |
| --- | --- |
| Vulnerability admission | Use the digest-pinned Trixie base in `Dockerfile`; do not disable scanning or weaken the policy. |
| Protected secret resolution | Validate the store's JSON syntax and string values, renderer access and exact reference names. Environment assignments do not belong in the JSON store. |
| Database migration | Django settings must initialize first. Old Gateway URL validation blocked Foundry mode until commit `6c5facc`; keep unused Gateway settings empty. |
| Application health | Allow `tulun-api` in `DJANGO_ALLOWED_HOSTS`; check runtime state if hosts are correct. Docker startup alone does not prove HTTP health. |
| Application readiness | Verify database access, selected-provider/client settings and the Samoan singleton configuration. Health passing does not imply readiness. |

The runner deliberately suppresses raw runtime output to protect secrets. Use the
fixed stage labels and metadata-only diagnostics; never publish generated env files,
raw renderer output, credentials or unredacted database errors.

## Documents

- [Discovery](docs/discovery.md): original architecture and required changes.
- [API and operations](docs/backend.md): schema, auth, configuration, local usage,
  persistence, supply chain, upstream updates, and limitations.
- [Platform handoff](docs/deployment-contract.md): exact container/runtime contract.
- [Verification](docs/verification.md): executed checks versus outstanding gates.

## Quick local checks (Python 3.12)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install poetry==2.2.1
poetry install --only main --no-root
python manage.py test --settings=tulun.test_settings
```

The ordinary suite mocks model requests or runs a local fake compatible endpoint;
it consumes no real model tokens. Optional PostgreSQL suite:

```bash
TULUN_TEST_DATABASE_URL='postgresql://USER:PASSWORD@HOST:5432/tulun_test' \
  python manage.py test --settings=tulun.test_settings
```

Use only a dedicated disposable test database; Django creates/drops a test database.

## Container contract

```text
Dockerfile: Dockerfile
Build context: .
Internal port: 8000
Health: GET /api/v1/health
Readiness: GET /api/v1/ready
Translation: POST /api/v1/translate
Migration: python manage.py migrate --noinput
Startup: gunicorn --config gunicorn.conf.py tulun.wsgi:application
```

Runtime secrets are external. PostgreSQL must be external to the API container.
The production image runs as UID/GID 10001, exposes no UI/Admin routes, and has no
hidden migrations, static serving requirement, host-published-port dependency, or
internal Caddy/Nginx. Root `prototype.yml` declares the agreed version-2 Custom Docker
contract; Main-Website generates runtime artifacts and owns migrations, private
networks, health/readiness admission and Caddy routing. The repository's local
Compose file is not used by the platform.

### Worker memory budget

For PDF segment callers, see [Frontend PDF integration](docs/frontend-pdf-integration.md)
for concurrency, timeout, retry and failure-handling requirements.

Gunicorn defaults to **one synchronous worker** for the manifest's **512 MiB**
memory budget. On October 15, 2026, VM kernel logs confirmed repeated container
cgroup OOM kills with the previous two-worker default, even while health checks
and some translations returned `200`. These logs do not establish a memory leak.

Publish this change and create a **new Tulun deployment at the updated commit**;
restarting the old image does not load the new default. If the deployed environment
explicitly sets `GUNICORN_WORKERS`, remove that override or set it to `1` through
the deployment configuration that supplies it. One synchronous worker handles
one request at a time, so translations can delay health checks; verify both under
representative load before treating the deployment as stable.

On the VM, replace `<container>` with the new Tulun container name:

```bash
docker stats --no-stream <container>
docker inspect --format 'MemoryLimit={{.HostConfig.Memory}} OOMKilled={{.State.OOMKilled}}' <container>
sudo journalctl -k --since "10 minutes ago" | grep -iE 'oom|out of memory|killed process'
```

Confirm the effective memory limit, exercise translations and health/readiness,
and check for new worker kills. A container-level `OOMKilled=false` is not enough
to rule out individual worker kills; inspect the kernel logs too. Increase the
memory budget only after measuring peak usage and checking VM capacity. Explicit
`GUNICORN_WORKERS` overrides remain supported from `1` to `4`, but additional
workers require a measured memory budget. Do not disable OOM protection.

Upstream academic material and evaluation notebooks remain under `eval/` (not in
the production image). Legacy UI and Google/HF/DSPy are development-only, optional
dependencies; they are not part of the MSD deployment surface.
