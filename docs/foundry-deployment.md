# Temporary direct Azure AI Foundry deployment

Direct Foundry support is an explicit operator-selected alternative while Gateway
key provisioning is unavailable. It does not repair provisioning or fall back
automatically. Requests in this mode bypass the Gateway's inspection, credential
registry, audit and per-client governance controls. Obtain the owning team's approval
and apply the required platform admission, logging and data-handling controls.

## Configure Main-Website

Commit and push the updated application and root `prototype.yml` to the selected
deployment branch before importing the manifest in Services & Configuration.
This checkout does not push or deploy automatically.

For service `tulun-api`, configure:

| Field | Value |
| --- | --- |
| `AI_PROVIDER` | `foundry` |
| `AZURE_FOUNDRY_BASE_URL` | `https://claude-sonnet-resource.services.ai.azure.com/openai/v1/responses` |
| `AZURE_FOUNDRY_API_STYLE` | `responses` |
| `AZURE_FOUNDRY_MODELS` | `gpt-6-luna` (the exact deployment name supplied by the operator) |
| `AZURE_FOUNDRY_API_KEY` | Protected reference name, e.g. `approved-tulun-foundry`; not the actual key. |
| `DJANGO_SECRET_KEY` | Existing protected Django secret reference. |
| `TULUN_API_KEY` | Separate protected caller key reference; never reuse the Foundry key. |
| `DJANGO_ALLOWED_HOSTS` | Public platform hostname, `tulun-api`, `localhost`, `127.0.0.1`. |
| `DATABASE_URL` | Platform managed. |

Save each field. Leave `AI_GATEWAY_*` empty for this deployment; they are no
longer required by the manifest. Do not use an Anthropic `/anthropic` endpoint,
Foundry project endpoint, `/models` endpoint, or a complete `/chat/completions` URL.
The supplied URL is a direct Foundry Responses endpoint, not the Governed AI
Gateway. The adapter normalizes it to `/openai/v1` internally and calls `/responses`
once. Responses requests use `store=false`, `background=false`, no streaming, no
automatic retries and bounded `max_output_tokens`. Incomplete, refused, empty,
oversized or unexpected tool outputs are not recorded as successful translations.
This does not claim that all other provider-side logging/retention is disabled.

Existing deployments can keep Chat Completions by using a resource root or
`/openai/v1` base with `AZURE_FOUNDRY_API_STYLE=chat_completions`. A full Responses
endpoint with a conflicting API style is rejected. This adapter supports only
OpenAI-compatible v1 APIs, not every Foundry model/API family. The configured
`gpt-6-luna` deployment is operator-supplied; its live availability is not verified.

## Inactive Gateway configuration

When `AI_PROVIDER=foundry`, `AI_GATEWAY_BASE_URL` is not used or URL-validated.
An old Gateway URL must not prevent Django initialization or migrations in
Foundry mode. Gateway mode still validates its own URL and never falls back to
Foundry. Clear the unused `AI_GATEWAY_BASE_URL`, `AI_GATEWAY_API_KEY` and
`AI_GATEWAY_MODELS` bindings in Services & Configuration to avoid confusion and
unnecessary resolution of an old protected reference.

## Store the actual key

An operator must store the actual resource key under `approved-tulun-foundry` in
the deployment VM's protected secret backend, as resolved by
`PROTOTYPE_SECRET_RENDERER`. There is no raw-secret upload field in the current
Custom Docker configuration screen. Verify the deployed renderer/backend location;
do not assume a repository-default JSON file is the active store.

Add the reference to `PROTOTYPE_CUSTOM_DOCKER_SECRET_REFS` in the running
Main-Website application's trusted environment. Merge with existing entries and
preserve the other approved references:

```dotenv
PROTOTYPE_CUSTOM_DOCKER_SECRET_REFS={"<prototype-id>":["approved-tulun-django","approved-tulun-caller","approved-tulun-foundry"]}
```

Use the registered prototype's database ID, not slug or service name. The example
Django/caller names must be replaced with the actual existing reference names.
The allowlist contains names only. Never place the actual Foundry key in this
JSON, manifests, `.env.example`, Git, build arguments, Actions inputs or logs.

For local Compose, copy `.env.example` to ignored `.env`, protect it with mode
`0600`, and enter the actual `AZURE_FOUNDRY_API_KEY` there. This local `.env` does
not configure the Main-Website deployment.

## Translation configuration and verification

Both translation and post-editing DB model fields must match
`AZURE_FOUNDRY_MODELS`. Provision/reconfigure explicitly with the selected
deployment names:

```bash
python manage.py configure_translation \
  --target-language-code mi --target-language-name 'Māori' \
  --translation-model gpt-6-luna \
  --post-editing-model gpt-6-luna
```

This command updates the singleton configuration, resets its post-edit prompt and
clears legacy DSPy state. Review existing data before running it. It makes no model
call. Use the returned configuration ID for authenticated translation requests.

The command and readiness check do not verify live key validity, model support or
network access. Follow the existing platform procedure to provision configuration
before readiness admission, then verify a controlled live translation and metadata
logs. A fresh empty DB still needs this explicit provisioning step; migrations alone
are insufficient. Local tests only use mocked/local HTTP providers and consume no
Foundry tokens.

## Return to the Gateway

Restore all three `AI_GATEWAY_*` settings and the approved Gateway key reference.
Set the DB models to approved Gateway aliases and change `AI_PROVIDER` to `gateway`
as a coordinated release. Redeploy and verify readiness and a controlled translation.
Remove/rotate the temporary Foundry credential according to the owning team's policy.
Missing selected-provider settings fail closed rather than using the other provider.

Provider API reference: Microsoft Learn, Azure OpenAI API version lifecycle,
`https://learn.microsoft.com/en-us/azure/ai-foundry/openai/api-version-lifecycle`.
