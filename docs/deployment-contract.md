# Main-Website handoff

```text
Dockerfile path: Dockerfile
Build context: .
Service name recommendation: tulun-api (platform-owned final choice)
Internal container port: 8000
Health path: /api/v1/health (GET, public, no database or model call)
Readiness path: /api/v1/ready (GET, public, DB + config, no model call)
Migration command: ["python", "manage.py", "migrate", "--noinput"]
Production startup command: ["gunicorn", "--config", "gunicorn.conf.py", "tulun.wsgi:application"]
Expected API path: POST /api/v1/translate (no trailing slash)
Suggested external path: POST /tulun/api/v1/translate
Required secret names: DJANGO_SECRET_KEY, DATABASE_URL, TULUN_API_KEY, AI_GATEWAY_API_KEY
Required non-secret names: AI_GATEWAY_BASE_URL, AI_GATEWAY_MODELS
Routing configuration: DJANGO_ALLOWED_HOSTS (platform hostname, localhost, 127.0.0.1)
Deployment mode: TULUN_MODE=msd (image default)
Persistence: dedicated externally persisted PostgreSQL database and application user
Host mounts: none required by this application
Host-published ports: not required for platform deployment
Runtime UID/GID: 10001:10001
```

Platform responsibilities:

1. Build/scan the image and pin the deployed image digest; supply runtime secrets,
   configuration, private application networking, and a dedicated PostgreSQL DB/user.
   `DATABASE_URL` includes PostgreSQL credentials and is a secret. Use verified TLS
   (`sslmode=verify-full` and trust material appropriate to operations) where required.
2. Run migrations explicitly with the same image/environment before admitting the
   new instance. Do not make image startup run migrations implicitly.
3. Provision the singleton translation configuration using the management command
   below. This explicit one-time/reconfiguration operation is not a migration.
   Never automatically overwrite an existing approved configuration on startup.
4. Forward `/tulun/api/v1/*` to root `/api/v1/*`, stripping the prefix. Preserve the
   expected Host and supply trusted `X-Forwarded-Proto`; remove client-provided
   forwarding headers first. Forwarded Host is intentionally not trusted. Forward a
   safe `X-Request-ID` if available. Do not expose the container directly to the Internet.
5. Enforce TLS, request-body/time limits and per-client rate/connection controls at
   Caddy/platform; only two synchronous translation workers by default. The app has
   bounded work but no distributed request-rate limiter or durable queue.
6. Verify health, readiness, normal single-prefix routing, caller authentication,
   translation with an approved test Gateway credential, and database persistence.
7. Keep Django Admin/UI disabled. API hosting has no static assets requirement.
   The deployment system must not run this repository's local Compose file.

```bash
python manage.py configure_translation \
  --target-language-code mi --target-language-name 'Māori' \
  --translation-model APPROVED_GATEWAY_ALIAS \
  --post-editing-model APPROVED_GATEWAY_ALIAS
```

Choose a language and model aliases approved by the owning team/Gateway. The command
returns the actual `configuration_id` needed by clients and validates the allowlist.
It never invokes an LLM. It resets the post-edit prompt and clears legacy DSPy state;
review before running it against existing data. Gateway base URL ends in `/v1`, for
example the privately configured address or platform-prefixed Gateway route. Never
point it to Foundry or supply a raw provider credential.

No schema migrations are added: the 19 upstream migrations remain unchanged. Rolling
back this application change does not remove columns. The old image still uses
SQLite and direct providers; returning to it is not a safe operational rollback
without restoring its database/configuration/runtime contract. PostgreSQL data
transfer is a separate controlled task; do not silently replace existing SQLite data.

## Registration manifest

The repository-root `prototype.yml` uses Main-Website's version-2 Custom Docker
contract. Commit and push this file to the deployment branch before registering
the existing repository in Prototype Admin; a local file alone is not visible to
the control plane. The manifest declares port, health/readiness, argv migrations,
resource limits and runtime reference requirements, never secret values.

Configure `DJANGO_ALLOWED_HOSTS` to include the public platform hostname and
`tulun-api` for private health/readiness probes. Bind the three application secret
references (`DJANGO_SECRET_KEY`, `TULUN_API_KEY`, `AI_GATEWAY_API_KEY`), plus the
platform-managed dedicated `DATABASE_URL`. Gateway URL and model aliases remain
operator-approved configuration, not baked-in deployment values.

The platform generates the route from the registered slug. A registration using
`translation-backend` is reached at `/translation-backend/api/v1/translate`, not
`/tulun/api/v1/translate`. The manifest strips either platform-owned prefix.

Gateway reachability/egress, least-privilege secret delivery, dedicated database
provisioning and production orchestration remain operational release checks. No
production resources are changed by adding the manifest.
