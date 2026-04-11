---
name: substack
description: "Retrieve posts from any Substack newsletter using its internal API. Use when asked to list, fetch, search, or download Substack articles/posts. Supports pagination, search, sorting, and full content retrieval for paid posts."
---

# Substack

Retrieve posts from any Substack newsletter via its internal API, with full authenticated access to paid/subscriber-only content.

Built using the `website-to-api` pattern. If this skill breaks, use the `website-to-api` meta-skill to re-discover the API.

## If This Breaks

This skill uses Substack's internal, undocumented API. If commands fail:

1. **Read the error** — 401/403 likely means expired cookie or renamed cookie.
2. **Re-discover** using the `website-to-api` meta-skill.
3. **Update this skill** — fix the script and SKILL.md with the new API shape.

Known past changes: the session cookie was renamed from `connect.sid` to `substack.sid`. The `COOKIE_NAME` constant in the script controls this.

## Prerequisites

- `SUBSTACK_SID` environment variable set to your `substack.sid` cookie value
- Python 3.9+, runs via `uv run`

## Getting the Cookie

1. Open Chrome DevTools (Cmd+Option+I) on any `substack.com` page
2. Go to Application > Cookies > `https://substack.com`
3. Find `substack.sid` (httpOnly, Secure) and copy its value
4. `export SUBSTACK_SID="<value>"`

The cookie lasts ~3 months and survives MFA unless you sign out.

### Verifying auth via Chrome extension

```javascript
// Run via javascript_tool on a newsletter tab
fetch('/api/v1/archive?sort=new&limit=1', { credentials: 'include' })
  .then(r => r.json())
  .then(data => { document.title = JSON.stringify({ ok: true, title: data[0]?.title }); })
  .catch(e => { document.title = 'ERROR: ' + e.message; });
```

## Script Location

`skills/substack/scripts/substack.py` (relative to plugin root)

## Commands

### list-posts

```bash
uv run skills/substack/scripts/substack.py list-posts https://www.lennysnewsletter.com
uv run skills/substack/scripts/substack.py list-posts https://www.lennysnewsletter.com --limit 30 --output json
uv run skills/substack/scripts/substack.py list-posts https://www.lennysnewsletter.com --sort top --limit 10
uv run skills/substack/scripts/substack.py list-posts https://www.lennysnewsletter.com --search "AI"
uv run skills/substack/scripts/substack.py list-posts lenny  # bare subdomain
```

| Option     | Default | Description                          |
|------------|---------|--------------------------------------|
| `--limit`  | 12      | Number of posts (auto-paginates >50) |
| `--offset` | 0       | Pagination offset                    |
| `--sort`   | new     | `new` or `top`                       |
| `--search` | (none)  | Full-text search query               |
| `--output` | table   | `table` or `json`                    |
| `--sid`    | (none)  | Cookie value (overrides env var)     |

### get-post

```bash
uv run skills/substack/scripts/substack.py get-post https://www.lennysnewsletter.com my-post-slug
uv run skills/substack/scripts/substack.py get-post https://www.lennysnewsletter.com my-post-slug --output html
uv run skills/substack/scripts/substack.py get-post https://www.lennysnewsletter.com my-post-slug --output json
```

| Option     | Default | Description                  |
|------------|---------|------------------------------|
| `--output` | summary | `summary`, `html`, or `json` |

### get-text

Fetch a post and save as Markdown with metadata header.

```bash
uv run skills/substack/scripts/substack.py get-text https://www.lennysnewsletter.com my-post-slug
uv run skills/substack/scripts/substack.py get-text https://www.lennysnewsletter.com my-post-slug --out ./article.md
```

| Option       | Default        | Description      |
|--------------|----------------|------------------|
| `--out / -o` | /tmp/<slug>.md | Output file path |

Newsletter argument accepts full URLs or bare subdomains (e.g. `lenny` → `https://lenny.substack.com`).

## API Reference

| Endpoint              | Method | Description       |
|-----------------------|--------|-------------------|
| `/api/v1/archive`     | GET    | List/search posts |
| `/api/v1/posts/<slug>`| GET    | Get a single post |

### Archive parameters

| Param    | Values                |
|----------|-----------------------|
| `sort`   | `new`, `top`          |
| `search` | any string            |
| `offset` | integer               |
| `limit`  | integer (max 50)      |

### Auth vs No-Auth

For `audience: "only_paid"` posts:
- **Without auth:** `body_html` truncated at paywall
- **With auth (paid subscriber):** full content returned
