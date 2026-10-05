# Verification evidence and remaining gates

Executed locally on 2026-10-05 UTC with isolated Python 3.12.15:

- 29 automated tests pass with SQLite, exercising actual spaCy glossary matching,
  Tantivy memory retrieval, existing prompt/post-edit pipeline, atomic persistence,
  JSON/auth/size/language/configuration validation, and safe metadata/errors.
- The same 29 tests pass using temporary local PostgreSQL 17.11; Django applies
  the existing migrations to a disposable test database.
- Real LiteLLM-to-local-HTTP fake Gateway tests verify custom prefixed /v1 routing,
  model name, separate credential, request ID, output limit, no retries for
  401/403/429/400/5xx, controlled malformed output, and no secret/payload printing.
- Native Gunicorn smoke: 3/3 checks pass (explicit PostgreSQL migrations; health and
  authenticated translation through fake Gateway; process restart and stored data).
- Locked main dependency scan after refresh: 91 packages, zero known findings. The spaCy model
  direct-URL artifact is skipped by pip-audit, not asserted vulnerability-free.
- Django system checks, migration-drift check (no new schema changes), Python/shell
  syntax, Poetry lock consistency and `git diff --check` pass. Poetry reports the
  pre-existing license-table deprecation warning; no formatter is configured.

## Not proven by these checks

- Docker image build/start/health/migration/container-replacement proof: Docker and
  daemon unavailable locally. Runnable isolated `scripts/runtime_smoke.py --docker`
  and CI gate supplied, but not represented as executed.
- Container vulnerability scan and image SBOM generation: tooling/real image not
  available in this environment. Script and CI supplied, not claimed executed.
- GitHub CI execution, publication, deployment and Main-Website integration.
- Live Governed AI Gateway (approved credential/model aliases, policy/classification,
  rate/token allowance, output quality). No live tokens or credentials used.
- Real target-language quality/accuracy, human approval for medical or other
  consequential content, database retention/privacy and production resource sizing.
- Existing SQLite-to-PostgreSQL data migration or production backups/restore.

## Outstanding operational risks

The fork exists on the MSD remote and upstream/base is recorded, but new changes
are local/uncommitted. Exact platform manifest schema remains unknown: no fabricated
manifest or host mounts. The single shared caller secret is constrained sandbox auth,
not per-consumer IAM/revocation/accounting. Admission/rate controls are platform-owned.
Global singleton configuration/shared memory is not tenant/language isolation.
BM25 corpus rebuild may require optimization after measured corpus/resource limits.
Legacy DSPy mode is not Gateway-adapted and is deliberately rejected by the API;
optional legacy UI compatibility is not validated as part of the MSD release.

Container/live/platform/supply-chain gates must pass before calling this deployment
complete. Automated tests and native process proof are not substitutes for them.
