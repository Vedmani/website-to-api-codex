---
name: website-to-api
description: "Discover and wrap a website's internal API using browser network inspection, sanitized HAR analysis, and browserless replay. Use when asked to reverse-engineer an undocumented web API, turn a browser workflow into a CLI, compare authenticated and unauthenticated behavior, or generate a reusable site-specific Codex skill."
---

# Website to API

Turn an authorized browser workflow into a tested HTTP client and an optional site-specific Codex skill.

## Operating Loop

1. Observe the smallest user-visible workflow that produces the desired data.
2. Prefer a user-supplied HAR, then distill candidate requests from it or live network traffic.
3. Reproduce the request browserlessly with the fewest necessary headers and no auth.
4. Compare browser, unauthenticated, and explicitly authenticated behavior.
5. Build and test a site-specific `uv run` client.
6. Generate a reviewable skill under `outputs/<site-name>-skill/`.
7. Ask before installing the generated skill.

Stop when the client works. Do not exhaustively map an API unless the user asks.

## Sensitive Data Handling

- Treat HARs, browser profiles, cookies, storage state, request bodies, and response bodies as sensitive.
- Never print or store credential values in reports, generated skills, source control, or shell history.

## Choose the Discovery Path

Use the first suitable path; keep the others available:

1. **Supplied or manually exported HAR (preferred):** analyze it directly. A user-controlled export from a fresh isolated browser session is the safest default because it avoids attaching automation to an existing browser. Do not modify or delete a user-supplied HAR.
2. **Live browser inspection:** use when no HAR exists and manual export is impractical, or when the user asks Codex to perform discovery. Load and follow the relevant browser skill, use an isolated profile, and inspect fetch/XHR traffic while performing the workflow.
3. **Sanitized HAR capture (optional):** use when the user wants automated capture, live logs are truncated or noisy, repeated comparison matters, or a durable discovery artifact is useful.
4. **HTML/bundle inspection:** use when browser capture stalls or the data is server-rendered. Fetch HTML and JavaScript bundles, search them with `rg`, and verify candidate endpoints directly.

Do not make a HAR a hard prerequisite. If importing one is unavailable, continue with the least invasive suitable fallback instead of reducing the requested capability.

Read [references/capture-and-har.md](references/capture-and-har.md) before capturing or importing a HAR. Read [references/api-patterns.md](references/api-patterns.md) for GraphQL, pagination, polling, SSE, WebSockets, uploads, and framework data.

## Distill a HAR

Generate a redacted JSON report:

```bash
python3 scripts/analyze_har.py work/site.har \
  --host target-site.example \
  --output work/discovery.json
```

The analyzer reports endpoint groups, query/header names, request and response shapes, pagination hints, status codes, and auth-material presence. It omits credential values and non-secret examples by default.

Capture a sanitized HAR only when useful:

```bash
uv run scripts/capture_har.py local 'https://target-site.example' work/site.har --headed
uv run scripts/capture_har.py cdp "$WEBSITE_TO_API_CDP_URL" work/site.har --goto 'https://target-site.example'
```

Use CDP only when the user explicitly authorizes attachment to that browser. The capture script never intentionally retains credential values, but a HAR can still contain personal response data; keep it private and remove task-created artifacts when no longer needed.

## Verify and Minimize the Request

Recreate the method, URL, query, and body without credentials. Add non-secret headers only when testing shows they are required. Do not assume an exact captured User-Agent, every browser header, or every cookie must be replayed.

Classify the result:

- A terminal request succeeds: document the endpoint as unauthenticated.
- A browser-created resource returns 404: create a fresh resource browserlessly before concluding auth is required.
- The terminal returns 401/403 or redacted data: verify browser-context behavior, then identify the minimum auth mechanism.
- A request succeeds only with state-changing setup: document that lifecycle and make client behavior explicit.

Read [references/auth-and-replay.md](references/auth-and-replay.md) before transferring auth or probing any endpoint that might mutate state.

## Build the Client

Use `assets/site-skill-template/scripts/client.py.template` as a starting point when it fits.

- Use `httpx`, `typer`, `rich`, and PEP 723 metadata.
- Pass auth through site-specific environment variables, not CLI flags or files.
- Do not send a browser User-Agent unless replay testing proves it necessary; make it configurable through an environment variable.
- Auto-paginate only after confirming limits and cursors.
- Bound error output and redact secret-like fields.
- Implement polling before optional streaming when an async workflow supports both.
- Test one successful request and one expected failure.

## Generate the Site Skill

After the client works, use `$skill-creator` to create or update the site-specific skill under:

```text
outputs/<site-name>-skill/
```

Adapt `assets/site-skill-template/`; do not leave placeholders. Include only required skill resources. The generated skill must contain:

- A trigger-rich `SKILL.md`
- Endpoint and request/response documentation
- Auth behavior, credential names, and env vars—or an explicit no-auth statement
- A tested client under `scripts/`
- Recovery guidance for undocumented API changes
- `agents/openai.yaml` with `policy.allow_implicit_invocation: false`

Validate the skill, run its client with `--help`, execute a real request, and verify no secrets or HARs are present.

## Install Only After Approval

Ask the user before installation. After approval, run:

```bash
uv run scripts/install_site_skill.py outputs/<site-name>-skill --approved-by-user
```

The installer validates before replacing anything and rejects secret-like artifacts. Do not use `--force` unless the user also approved replacing an existing installed skill.

## Completion Checklist

- The client succeeds browserlessly and handles one negative case.
- Auth versus no-auth behavior is documented from evidence.
- Credential values are absent from logs, reports, scripts, and skills.
- Consequential endpoints were not replayed without approval.
- Generated skill validation passes and `allow_implicit_invocation` is false.
- Task-created browser sessions are closed.
- The final response reports generated paths, validation commands, and install status.

## If Discovery Breaks

1. Re-run the smallest workflow and compare a fresh redacted report.
2. Check for endpoint, schema, auth-name, pagination, or async-lifecycle changes.
3. Update the generated client and skill from observed evidence rather than guessing.
