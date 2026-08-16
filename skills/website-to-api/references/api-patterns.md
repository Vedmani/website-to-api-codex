# API Discovery Patterns

Use this reference when the workflow is not a simple JSON fetch.

## Framework and Bundle Discovery

- Inspect `__NEXT_DATA__`, Remix loaders, Nuxt payloads, hydration state, and page globals before assuming an endpoint is required.
- Fetch HTML and JavaScript bundles with `curl`, then use `rg` for `fetch(`, `/api/`, `graphql`, `operationName`, `cursor`, `subscribe`, `EventSource`, and WebSocket URLs.
- Verify strings from minified bundles with a real request; dead code and alternate environments are common.

## GraphQL

- Record the endpoint, operation name, variables, and whether persisted-query hashes are required.
- Preserve the operation document or hash, not unrelated requests from the same batch.
- Inspect `errors` even when HTTP status is 200.
- Document cursor locations such as `pageInfo.endCursor` and `hasNextPage`.

## Pagination

- Identify offset/limit, page/page-size, cursor, continuation-token, or link-header behavior.
- Determine maximum page size and stable sort order before auto-pagination.
- Stop on an empty page, missing next cursor, repeated cursor, or user limit.
- Deduplicate only using a stable documented/observed identifier.

## Submit, Poll, and Stream

- Separate resource creation, status polling, result reading, cancellation, and streaming endpoints.
- Prefer bounded polling with an explicit timeout and backoff when it yields complete results.
- For SSE, document event names, `data` JSON shapes, completion markers, and reconnect behavior.
- For WebSockets, document the HTTP setup/auth handshake and message protocol separately. HAR files do not contain complete WebSocket frame history; use live CDP/network tooling.
- Preserve citations, references, or attachment metadata separately from text chunks.

## Uploads and Downloads

- Identify pre-signing, multipart upload, commit/finalize, and download URL steps separately.
- Treat signed URLs and upload tokens as secrets even when short-lived.
- Do not upload real user data merely to test an endpoint; use an approved disposable fixture.
- Stream large downloads to disk and verify content type, size, and filename handling.

## Server-Rendered Workflows

If no fetch/XHR request exists, extract the HTML or hydration payload instead of forcing an API interpretation. Generate a scraper only when that is the durable interface the site actually exposes.
