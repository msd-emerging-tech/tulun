# Phase 0 discovery (2026-10-05 UTC)

Inspected before application changes (2026-10-06 in New Zealand local time). MSD remote: `tulun-origin`,
`https://github.com/msd-emerging-tech/tulun.git`. Public upstream:
`https://github.com/raphaelmerx/tulun.git`. Both main refs resolved to
`e81f7a7291b3d7636818be7c7c35f50811dd0747` at discovery. No upstream writes.

| Area | Existing implementation |
| --- | --- |
| Python | `>=3.12,<3.13`; Docker uses Python 3.12 slim. |
| Django | Range `>=5.1.7,<6`; lock pins 5.1.7. |
| Database | SQLite at `/app/db.sqlite3`; 19 Django migrations. |
| Models | CustomUser, GlossaryEntry, CorpusEntry, Translation, SystemConfiguration, EvalRow. Translation has glossary/memory many-to-many references and nullable creator. |
| Translation memory | CorpusEntry rows; in-memory Tantivy BM25 index rebuilt per retrieval. Separate Google/HF JSON first-pass caches under relative `datafiles/`. |
| Glossary | Global English keys matched using spaCy lemmas, tokens, and bigrams. No project/language scoping. |
| Initiation | Browser `/translate/` SSE requests, session/config-dependent authentication, `source_text` in query string. |
| Domain classes | TranslatorMixin, TranslatorGoogle, TranslatorHuggingFace, Message, Correction in `translations/utils.py`. |
| Pipeline | Initial translation, glossary lookup, BM25 examples, initial translations of examples, prompt construction, post-editing, corrections, persisted Translation and associations. |
| LiteLLM | Locked 1.63.7; direct completion using config.post_editing_model; no custom endpoint, deadline or output cap. |
| Model selection | Singleton SystemConfiguration: Google Translate first pass, Gemini post-editing; HF alternative. Optional DSPy state takes precedence over hand-built prompt and globally initializes Gemini. |
| Environment | python-dotenv in translation/DSPy modules; settings read os.environ. Debug defaults on; hardcoded fallback Django key. Optional Sentry enables default PII. |
| Docker | Poetry install, redundant unlocked torch/model downloads, collectstatic, root user; Daphne ASGI on 8008. No dockerignore. |
| Compose | Local SQLite/static bind mounts, prod.env, host 8008; platform must not use this file. |
| Static | Admin/UI assets collected into staticfiles; no production serving configured. API itself requires none. |
| Admin | Standard Django Admin plus custom CSV imports/config editing; public route exists. UI depends on singleton config/templates. |
| WSGI/ASGI | Both standard entrypoints present; Django supports WSGI API without a second framework. |
| Tests | translations/tests.py is an empty scaffold. No meaningful automated coverage. |
| HTTP APIs | Session/permission-protected form POST /api/corpus-entry/; plaintext /healthcheck/; SSE UI translation. No authenticated JSON translation API. |

## Required adaptation

Reuse TranslatorMixin prompts/corrections, glossary, BM25, and persistence. Make
configuration request-scoped, avoiding stale global lazy state. Add a Gateway
first-pass adapter to the existing hierarchy: Google/HF defaults cannot satisfy
provider-credential-free operation. Force both generation stages through the
Gateway in default MSD mode; reject Google/HF/DSPy configurations, never fall back.
Retain those integrations only in an explicit optional legacy development mode.

Add bounded authenticated root-hosted JSON routes, controlled errors, safe metadata
logs, health/readiness, external PostgreSQL, non-root Gunicorn on 8000, locked
production dependencies, tests, and supply-chain checks. No schema change needed.
Source is English, target comes from an explicitly selected singleton config;
glossary/memory are globally shared, not a multilingual multi-tenant project service.

## Initial verification constraints

Host Python is 3.13, not supported 3.12; tests need an isolated supported runtime.
Docker is absent and disk constrained. Image build, container restart, PostgreSQL
container persistence, live Gateway, and platform deployment require separate proof.
Main-Website custom Docker schema is not supplied: document the handoff rather than
inventing a deployment manifest. Do not modify Main-Website.
