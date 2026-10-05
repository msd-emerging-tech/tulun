# Tulun — MSD backend fork

This MSD-controlled fork adapts Tulun's existing English-to-configured-language
translation and post-editing pipeline into a bounded, authenticated Django API.
Both model stages use the Governed AI Gateway; no Foundry/Google/Gemini key is
required. There is no direct-provider fallback in MSD mode.

Public upstream: `https://github.com/raphaelmerx/tulun` (MIT).
Fork base: `e81f7a7291b3d7636818be7c7c35f50811dd0747` (`Update README.md`).
MSD remote: `https://github.com/msd-emerging-tech/tulun.git` (`tulun-origin`).
The `upstream` Git remote is preserved locally; cloning does not preserve extra
remotes, so add it explicitly when needed. No commits or pushes are performed by
the implementation.

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
internal Caddy/Nginx. Main-Website is not modified. No platform manifest is invented
before its custom Docker schema is agreed.

Upstream academic material and evaluation notebooks remain under `eval/` (not in
the production image). Legacy UI and Google/HF/DSPy are development-only, optional
dependencies; they are not part of the MSD deployment surface.
