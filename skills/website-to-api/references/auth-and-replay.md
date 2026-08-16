# Authentication and Replay

Use this reference before transferring authentication or probing endpoints that may change state.

## Minimal Replay Order

1. Reproduce the exact method, URL, query parameters, and body without auth.
2. Add `Accept` or `Content-Type` when required by the payload.
3. Add `Origin` or `Referer` only when the server checks them.
4. Add a configurable browser User-Agent only after a default client is rejected.
5. Add the minimum verified cookie or authorization mechanism last.

Do not copy browser-only transport headers, request IDs, tracing headers, Client Hints, or every cookie into the client.

## Evidence Matrix

| Browser context | Terminal | Interpretation |
|---|---|---|
| succeeds | succeeds | Endpoint is public or auth is irrelevant for this resource |
| succeeds | 401/403 | Authentication or browser-bound checks are likely required |
| full data | redacted data | Auth changes authorization scope |
| succeeds | 404 | Resource may be session-scoped; create a fresh resource before deciding |
| fails | fails | Endpoint, payload, prerequisite state, or workflow identification is wrong |

Record status codes, response fields, and redaction differences. Do not infer auth solely from the presence of cookies in a browser request.

## Credential Transfer

- Prefer one site-specific environment variable per required credential.
- Accept a raw `Cookie` header through an environment variable only when multiple cookies are demonstrably required.
- Never accept secrets as positional arguments or recommend putting them in shell history.
- Report credential names and whether they were present, never values.
- Do not export browser storage state into a generated skill.
- Expect credentials to expire and document the recovery path.

## Consequential Requests

Treat POST, PUT, PATCH, and DELETE as potentially consequential even when their names appear harmless. GET requests can also trigger side effects on poorly designed services.

Before replaying a consequential endpoint:

1. Explain the expected external effect and exact target.
2. Obtain explicit user approval unless the request is already an unavoidable, clearly authorized step in their requested workflow.
3. Prefer a disposable test resource or documented dry-run mode.
4. Avoid automatic retries unless idempotency is established.
5. Preserve idempotency keys when required, but treat their values as sensitive.

Never test purchase, payment, messaging, account, permission, or deletion endpoints merely to prove discovery.

## Failure Handling

- `401`: missing, expired, or malformed authentication.
- `403`: insufficient authorization, CSRF/origin checks, policy controls, or bot defenses; do not attempt bypasses.
- `404`: wrong path or a session-/tenant-scoped resource.
- `409`: state or idempotency conflict.
- `429`: stop, honor retry guidance, and lower request rate.
- HTML instead of JSON: inspect redirects, login responses, WAF pages, and content type before parsing.
