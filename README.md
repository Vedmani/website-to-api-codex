# website-to-api

A local Codex plugin for reverse-engineering website internal APIs and generating reviewable site-specific Codex skills.

This project began as a fork of [hamelsmu/website-to-api](https://github.com/hamelsmu/website-to-api) and retains that work's Git history. It has since been substantially redesigned as a standalone Codex plugin.

## What This Does

Most websites do not expose public APIs, but modern web apps usually fetch data from internal endpoints. This plugin provides:

1. A meta-skill, `website-to-api`, for discovering and wrapping those internal APIs
2. A deterministic HAR analyzer that emits redacted discovery JSON
3. Optional sanitized HAR capture for isolated local or explicitly authorized CDP browsers
4. Website-to-api-specific templates for generated site skills
5. A Python client template that runs with `uv run` using PEP 723 inline metadata
6. A validate-first, approval-gated installer for generated site skills

## How It Works

The pattern is:

1. **Discover** - Navigate to a website with Codex browser automation, inspect requests, and identify internal endpoints
2. **Distill** - Group candidate endpoints from live traffic or a supplied/sanitized HAR
3. **Authenticate** - Verify which requests work with the browser session and what, if any, cookie or header is needed by scripts
4. **Script** - Build a CLI that calls the discovered endpoints using auth supplied through environment variables
5. **Generate** - Create a reviewable site-specific skill under `outputs/<site-name>-skill/`
6. **Approve and install** - Validate first, then ask before copying the generated skill into `${CODEX_HOME:-$HOME/.codex}/skills/<site-name>`

## Available Skills

| Skill | Description |
|-------|-------------|
| `website-to-api:website-to-api` | Meta-skill for discovering and wrapping a website's internal API |

## Usage

Ask Codex:

> Use `website-to-api` to figure out the API for this site. I want to list and download content from it.

Codex will use the skill to:

- Prefer `agent-browser` with a dedicated local automation profile when CDP/network/cookie capabilities help
- Prefer an existing or manually exported HAR from a fresh isolated browser session as the safest discovery intake
- Keep live browser inspection available when manual export is impractical or Codex is asked to perform discovery
- Keep sanitized local/CDP capture optional, using it only when requested or when logs are noisy/truncated or repeatable comparison is useful
- Fall back to terminal bundle/API verification when browser automation gets sticky or overlong
- Identify endpoint URLs, methods, parameters, request bodies, and response shapes
- Test authenticated browser requests against unauthenticated terminal requests
- Generate a reviewable site-specific client and skill
- Ask before installing the generated skill into Codex's personal skills directory

## Browser Profile

For `agent-browser` workflows, use a dedicated profile instead of a personal daily browser profile:

```bash
export WEBSITE_TO_API_BROWSER_PROFILE="$HOME/.agent-browser/profiles/website-to-api"
agent-browser --profile "$WEBSITE_TO_API_BROWSER_PROFILE" --headed open "https://example.com"
```

Use headed mode for first-time login, 2FA, consent screens, or debugging. Use headless mode only after the profile is authenticated and the workflow is repeatable. Close the active session before switching between headed and headless runs.

When the browser task is complete, close the automation session and verify cleanup:

```bash
agent-browser close
agent-browser session list
```

The profile directory and any saved state files contain auth material and should be treated as secrets.

## HAR Analysis and Optional Capture

Analyze a HAR without printing credential values or response samples:

```bash
python3 skills/website-to-api/scripts/analyze_har.py work/site.har \
  --host example.com \
  --output work/discovery.json
```

Capture is optional. Use it when a reproducible artifact is more useful than one-off live network inspection:

```bash
uv run skills/website-to-api/scripts/capture_har.py local \
  'https://example.com' work/site.har --headed
```

The capture script redacts credential-like values and writes mode `0600`, but arbitrary response bodies can still contain personal information. Keep HARs private, never install them inside generated skills, and delete task-created captures when they are no longer needed.

## Generated Site Skills

Generated site skills are created first in a reviewable workspace path:

```bash
outputs/<site-name>-skill/
```

After the generated skill is validated, Codex should ask for user approval before installing it. With approval, install it into personal Codex skills:

```bash
uv run skills/website-to-api/scripts/install_site_skill.py \
  outputs/<site-name>-skill \
  --approved-by-user
```

The default installed location is:

```bash
${CODEX_HOME:-$HOME/.codex}/skills/<site-name>
```

Run a generated skill before installation:

```bash
uv run outputs/<site-name>-skill/scripts/client.py --help
```

Run an installed skill:

```bash
uv run "${CODEX_HOME:-$HOME/.codex}/skills/<site-name>/scripts/client.py" --help
```

Generated skills should contain only skill files and resources: `SKILL.md`, `agents/openai.yaml`, `scripts/`, `references/`, or `assets/` as needed. Do not add README files, AGENTS files, changelogs, installation guides, or other auxiliary docs inside generated skills.

Generated website-to-api skills should set `policy.allow_implicit_invocation: false` in `agents/openai.yaml` so Codex uses them only when explicitly invoked by the user.

## Development

Templates for generated site skills live in two places:

- `skills/website-to-api/assets/site-skill-template/` for the installed plugin skill
- `templates/site-skill-template/` as repo-development convenience

Keep the two template trees byte-for-byte identical. The installed skill's asset copy is canonical.

## Testing

Validate the meta-skill:

```bash
uv run --with pyyaml python \
  "${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py" \
  skills/website-to-api
```

Validate the plugin manifest:

```bash
uv run --with pyyaml python \
  "${CODEX_HOME:-$HOME/.codex}/skills/.system/plugin-creator/scripts/validate_plugin.py" \
  .
```

Run behavioral tests:

```bash
uv run --with pytest --with pyyaml pytest -q
```

For regression testing, start a clean projectless Codex thread and ask it to use `website-to-api` on a real site. The test should verify that the downstream thread:

- Uses the installed plugin
- Generates a working client and skill under `outputs/`
- Validates the generated skill
- Asks before installing it
- Closes any `agent-browser` sessions

## Design Principles

- **Browser-first auth**: Use the browser session to verify authenticated behavior before asking for manual cookie extraction.
- **HAR-first without capability loss**: Prefer a supplied or manually exported HAR, while retaining live inspection, isolated local capture, authorized CDP, and HTML/bundle fallbacks.
- **Redacted artifacts**: Discovery reports expose names and schemas by default, not credential or personal values.
- **Discovery budget**: Stop tracing once enough endpoint, auth, and response-shape information exists to build a wrapper.
- **Approval-gated install**: Generated site skills are not installed until the user approves.
- **No secrets in code or shell history**: Auth cookies, tokens, and credentials must be passed through environment variables and never committed.
- **Resilient to change**: Internal APIs are undocumented and can break; every site-specific skill should include recovery instructions.
- **Self-contained scripts**: Generated clients should use PEP 723 inline metadata so they run with `uv run` without a package install step.
