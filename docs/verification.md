# Verification evidence and remaining gates

## Container base remediation: 2026-10-14

The deployed image from Tulun commit `40a8316` was rejected before runtime
provisioning because the scanner reported these Bookworm operating-system packages:

| Finding | Package in rejected image |
| --- | --- |
| `CVE-2025-7458` | `libsqlite3-0` `3.40.1-2+deb12u2` |
| `CVE-2023-45853` | `zlib1g` `1:1.2.13.dfsg-1` |

Both Docker stages now use the same digest-pinned official Python
`3.12.15-slim-trixie` base instead of Bookworm. Python version, locked application
dependencies, non-root runtime identity and platform vulnerability policy are unchanged.
No scanner ignore rule or increased vulnerability allowance has been added.

The official Docker registry manifest and its Linux/amd64 layer package metadata
were inspected without building or running a container. The selected base contains
`libsqlite3-0` `3.46.1-7+deb13u2` and `zlib1g`
`1:1.3.dfsg+really1.3.1-1+b1`; Debian's security tracker lists the Trixie source
versions as fixed for the respective findings. For the Bookworm zlib report,
Debian notes that the vulnerable MiniZip component is not built into its binary
packages; the remediation still replaces the base rather than disabling scanning.

All 57 local tests pass, including a regression check that both stages share a
digest-pinned Python 3.12 Trixie base. `git diff --check` also passes. A complete
rebuilt Tulun image scan, container compatibility
and live deployment still require Docker-capable CI/the trusted runner. The registry
metadata check is not a full-image vulnerability scan or proof that no other CVEs exist.

Publish the Dockerfile change, create a new prototype deployment at the new Tulun
commit and inspect its vulnerability evidence before runtime admission. Do not rerun
the failed snapshot at `40a8316`; that revision still contains the Bookworm Dockerfile.

References:
- `https://security-tracker.debian.org/tracker/CVE-2025-7458`
- `https://security-tracker.debian.org/tracker/CVE-2023-45853`

## Direct Foundry support: 2026-10-13

- All 56 automated API, settings and transport tests pass locally on SQLite,
  including both model stages in Foundry mode without Gateway credentials,
  readiness, independent caller auth and explicit configuration provisioning.
- Real LiteLLM-to-local-HTTP tests verify `/openai/v1/chat/completions` and
  `/openai/v1/responses`, selected
  key and model, request ID, bounded output, sanitized failures and no retries.
  Missing Foundry settings, unknown providers and unapproved deployments never
  fall back to the Gateway or make a model request.
- Responses tests preserve the supplied `gpt-6-luna` deployment name, require
  completed text output, allow reasoning before text and reject refusals,
  incomplete/failed responses and unexpected tool output. Requests explicitly
  disable response storage and background execution.
- `.env.example` uses the supplied `claude-sonnet-resource` Responses endpoint
  and `gpt-6-luna`; configuration tests verify endpoint normalization and API style.
- The updated root manifest passes Main-Website's actual Custom Docker parser.
  `AI_PROVIDER` is required; both provider-specific groups are optional at platform
  admission and selected-provider completeness is enforced by application readiness.
- Django checks, migration-drift check and `git diff --check` pass. No database
  schema or dependency changes are required.
- No actual Foundry key was supplied. The operator-supplied endpoint and deployment
  were configured but not contacted or verified live. VM
  secret installation, publication, image build, Main-Website deployment,
  production network access and live translation remain unverified.

## Original Gateway verification

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
