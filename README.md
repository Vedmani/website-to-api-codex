# website-to-api

A [Claude Code](https://docs.anthropic.com/en/docs/claude-code) plugin for reverse-engineering website internal APIs using Chrome browser automation.

## What This Does

Most websites don't have public APIs, but they all have internal ones. This plugin provides:

1. **A meta-skill** (`website-to-api`) that teaches Claude how to discover and wrap any website's internal API
2. **Site-specific skills** (like `substack`) that implement the pattern for known sites
3. **Templates** for quickly adding new sites

## How It Works

The pattern is:

1. **Discover** — Navigate to a website using the [Claude in Chrome](https://chromewebstore.google.com/detail/claude-in-chrome/) extension, inspect network requests, and find internal API endpoints
2. **Authenticate** — Extract httpOnly session cookies from the browser to use in scripts
3. **Script** — Build a CLI that calls the discovered endpoints with the extracted cookies
4. **Adapt** — When APIs change (they're internal and undocumented), re-discover and update

## Installation

Add this plugin to your Claude Code project:

```bash
git submodule add https://github.com/hamelsmu/website-to-api.git
```

## Available Skills

| Skill | Description |
|-------|-------------|
| `website-to-api:website-to-api` | Meta-skill: how to discover and wrap any website's internal API |
| `website-to-api:substack` | Retrieve posts from any Substack newsletter (list, search, full text) |

## Usage

### Discovering a new site's API

Ask Claude:
> "Can you figure out the API for [website]? I want to be able to list and download content from it."

Claude will use the `website-to-api` meta-skill to:
- Navigate to the site via Chrome
- Inspect network requests to find API endpoints
- Test authentication
- Build a script to call those endpoints

### Using the Substack skill

```bash
# Set your auth cookie (extract from Chrome DevTools > Application > Cookies > substack.com)
export SUBSTACK_SID="your-cookie-value"

# List recent posts
uv run skills/substack/scripts/substack.py list-posts https://www.lennysnewsletter.com --limit 20

# Download a post as Markdown
uv run skills/substack/scripts/substack.py get-text https://www.lennysnewsletter.com some-post-slug
```

## Adding a New Site

1. Copy the template: `cp -r templates/site-skill-template skills/your-site`
2. Use the `website-to-api` meta-skill to discover the site's API
3. Fill in the SKILL.md and script with the discovered endpoints
4. Submit a PR

## Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI
- [Claude in Chrome](https://chromewebstore.google.com/detail/claude-in-chrome/) extension (for API discovery and auth verification)
- Python 3.9+ and [uv](https://docs.astral.sh/uv/) (scripts use PEP 723 inline metadata)

## Design Principles

- **Browser-first auth**: Use the Chrome extension to handle authentication. The browser already has the user's session — don't ask humans for what the browser can provide.
- **Resilient to change**: Internal APIs break. Every site skill includes recovery instructions and references the meta-skill for re-discovery.
- **No secrets in code**: Auth cookies are always passed via environment variables, never stored in skill files or scripts.
- **Self-contained scripts**: Each script uses PEP 723 inline metadata so it runs with just `uv run` — no install step.
