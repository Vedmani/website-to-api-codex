---
name: website-to-api
description: "Reverse-engineer a website's internal API using Chrome browser automation. Use when asked to discover, wrap, or build a programmatic interface for a website that doesn't have a public API. Guides the process of finding endpoints, extracting auth, and building scripts."
---

# Website to API

A systematic approach to discovering and wrapping any website's internal API using Chrome browser automation (Claude in Chrome extension).

## When to Use This Skill

- The user wants to programmatically access data from a website that has no public API
- You need to figure out how a website fetches its data internally
- You need to extract authentication cookies to use in scripts
- A site-specific skill (e.g. `substack`) has broken and needs re-discovery

## The Pattern

Every modern web application fetches data from internal API endpoints. This skill teaches a repeatable 4-step process to discover and wrap those endpoints.

### Step 1: Discover Endpoints

Navigate to the target website using the Chrome extension and observe what API calls the page makes.

**Tools needed:**
```
ToolSearch("select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__javascript_tool,mcp__claude-in-chrome__read_network_requests,mcp__claude-in-chrome__get_page_text,mcp__claude-in-chrome__read_page")
```

**Procedure:**

1. **Get tab context and navigate:**
   ```
   mcp__claude-in-chrome__tabs_context_mcp(createIfEmpty=true)
   mcp__claude-in-chrome__navigate(url="https://target-site.com", tabId=TAB_ID)
   ```

2. **Enable network tracking, then trigger actions:**
   ```
   mcp__claude-in-chrome__read_network_requests(tabId=TAB_ID)  // starts tracking
   ```
   Navigate or interact with the page to trigger API calls, then read:
   ```
   mcp__claude-in-chrome__read_network_requests(tabId=TAB_ID, urlPattern="api")
   ```

3. **Inspect page globals for config:**
   ```javascript
   // Run via javascript_tool — look for app config, API base URLs, user info
   JSON.stringify(Object.keys(window).filter(k =>
     k.includes('config') || k.includes('api') || k.includes('app') || k.startsWith('__')
   ));
   ```

4. **Check for framework data (Next.js, etc.):**
   ```javascript
   // Next.js apps embed data in __NEXT_DATA__
   const nd = document.getElementById('__NEXT_DATA__');
   nd ? JSON.stringify(Object.keys(JSON.parse(nd.textContent))) : 'not Next.js';
   ```

5. **Try common API patterns:**
   ```javascript
   // Most sites use /api/v1/ or similar
   fetch('/api/v1/...', { credentials: 'include' })
     .then(r => r.json())
     .then(data => { document.title = JSON.stringify(Object.keys(data)); });
   ```

6. **Document what you find** — endpoints, parameters, response shapes.

### Step 2: Extract Authentication

Most sites use httpOnly session cookies that JavaScript cannot read. The browser sends them automatically with `fetch()` using `credentials: 'include'`.

**Verify auth works:**
```javascript
// Run via javascript_tool on the target site
fetch('/api/v1/some-endpoint', { credentials: 'include' })
  .then(r => r.json())
  .then(data => { document.title = JSON.stringify({ authenticated: true }); })
  .catch(e => { document.title = 'ERROR: ' + e.message; });
```

**Compare auth vs no-auth:**
```bash
# Unauthenticated (from terminal)
curl -s 'https://target-site.com/api/v1/endpoint' | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(str(d)))"
```
Compare the response size/content with the browser-based fetch to identify what auth adds.

**Find the cookie name:**
- Check `window._analyticsConfig` or similar globals for site metadata
- Search the web for "{site} API authentication cookie name"
- Common patterns: `connect.sid`, `{site}.sid`, `session`, `_session_id`
- The cookie is typically httpOnly on the site's domain or a parent domain

**For script usage, the user must extract the cookie value once:**
1. Open Chrome DevTools (Cmd+Option+I) on the target site
2. Go to Application > Cookies > find the auth cookie
3. Export as an environment variable: `export SITE_AUTH_COOKIE="<value>"`

### Step 3: Build the Script

Create a Python CLI script using PEP 723 inline metadata (runs via `uv run`, no install needed).

**Script template:** See `templates/site-skill-template/scripts/client.py.template`

**Key principles:**
- Use `httpx` for HTTP, `typer` for CLI, `rich` for display, `markdownify` for HTML→MD
- Accept auth via env var or `--sid`/`--cookie` flag
- Auto-paginate when the API has offset/limit
- Include a `get-text` command that fetches content and saves as Markdown
- Print the output file path to stdout for piping

### Step 4: Write the Skill

Create a SKILL.md that documents:
- The specific endpoints discovered
- The auth cookie name and how to extract it
- CLI commands with examples
- A **recovery section** for when the API changes

**Every site-specific skill MUST include this section:**

```markdown
## If This Breaks

This skill uses an internal, undocumented API. If commands fail:

1. Read the error — 401/403 likely means expired cookie or renamed cookie
2. Re-discover using the `website-to-api` meta-skill
3. Update this skill's SKILL.md and scripts with the new API shape
```

## Critical Rules

### Do
- Use the browser as the authenticated client — it handles cookies automatically
- Write results to files, not `document.title` (which truncates and corrupts data)
- Use `get_page_text` for extracting rendered page content — it's simpler than transferring HTML through JavaScript
- Store cookie values in env vars, never in skill files or scripts
- Compare authenticated vs unauthenticated responses to understand what auth provides
- Document the auth cookie name so it can be updated if the site renames it

### Don't
- Don't ask the human for help with things the Chrome extension can verify (auth status, endpoint discovery, response inspection)
- Don't rely on `document.title` for data larger than ~500 chars — it truncates silently and causes data corruption
- Don't reconstruct or summarize API data from truncated strings — show exact API responses
- Don't store any auth tokens, cookie values, or credentials in skill files
- Don't assume API shapes are permanent — always include recovery instructions
