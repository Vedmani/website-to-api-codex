# Capture and HAR Handling

Use this reference when importing, recording, or analyzing HTTP Archive traffic.

## Selection

- Prefer a user-supplied or manually exported HAR and leave the original untouched. A fresh isolated/incognito session limits unrelated cookies, history, and traffic.
- If no HAR exists, offer manual export first when it will not block the task.
- Use live browser network inspection when manual export is impractical or the user asks Codex to perform discovery.
- Capture a HAR automatically only when requested or when logs truncate, multiple runs must be compared, or endpoint grouping will save time.
- Use the local capture mode for a new isolated Chromium context.
- Use CDP mode only for an explicitly authorized existing browser. It attaches and does not close the browser it does not own.

HAR-first is a workflow preference, not a capability gate. Fall back to live inspection, local capture, CDP, or HTML/bundle analysis as the target requires.

## Manual Export

Use the browser's Network panel in a fresh isolated/incognito session, enable preservation if the workflow navigates, perform only the smallest relevant workflow, then export a HAR. Prefer an export option that omits sensitive data when the browser offers one.

Treat even a sanitized export as sensitive: URLs, request bodies, and response bodies may still contain personal or proprietary data. Keep the file local to the task and analyze it into a redacted report before sharing findings.

## Analyze an Existing HAR

```bash
python3 scripts/analyze_har.py work/site.har --host example.com -o work/discovery.json
python3 scripts/analyze_har.py work/site.har --host example.com --format text
```

Add `--include-examples` only when concrete non-secret query or header values are required. Even redacted reports may contain endpoint names and response schemas; keep them in task-local `work/` unless the user requests a deliverable.

## Capture Locally

```bash
uv run scripts/capture_har.py local 'https://example.com' work/site.har --headed
```

The script first tries Playwright's bundled Chromium, then system Chrome. If neither is available, install the Playwright browser with `uv run --with playwright playwright install chromium` or pass an installed channel such as `--channel chrome`.

For deterministic interactions, provide an actions JSON file:

```json
[
  {"type": "fill", "selector": "input[name=search]", "value": "dune"},
  {"type": "sleep", "seconds": 2},
  {"type": "press", "selector": "input[name=search]", "key": "Enter"},
  {"type": "wait_for_selector", "selector": "main", "timeout_ms": 15000}
]
```

```bash
uv run scripts/capture_har.py local 'https://example.com' work/site.har \
  --actions work/actions.json --wait 3
```

Use live browser automation instead when login, SSO, MFA, consent, CAPTCHA, downloads, or manual intervention is required.

## Capture Through CDP

```bash
export WEBSITE_TO_API_CDP_URL='ws://authorized-host/devtools/browser/...'
uv run scripts/capture_har.py cdp "$WEBSITE_TO_API_CDP_URL" work/site.har \
  --goto 'https://example.com' --actions work/actions.json --wait 3
```

Never place a CDP URL containing credentials directly in a committed file or generated skill. Do not attach to the user's everyday browser unless they explicitly requested that browser context.

## Data Handling

- Capture writes mode `0600` and redacts cookie, authorization, CSRF, session, password, API-key, and token-like fields.
- Sanitization cannot prove that arbitrary response text contains no personal data.
- Never commit HAR files, copy them into generated skills, or expose them as final deliverables by default.
- Delete task-created raw temporary files immediately after sanitization.
- Do not delete or rewrite a HAR supplied by the user.
- Close only browser sessions owned by the current task.

## Empty or Misleading Captures

- Add a trailing wait for debounced requests.
- Confirm the interaction actually fires fetch/XHR traffic.
- Server-rendered data may require HTML extraction instead.
- A service worker, popup, iframe, or WebSocket may require live CDP inspection rather than standard HAR analysis.
- Narrow by host after capture instead of assuming every third-party JSON request belongs to the target API.
