# website-to-api

## Overview

Codex plugin for reverse-engineering website internal APIs using browser automation and generating reviewable site-specific skills.

## Structure

- `skills/website-to-api/` - Meta-skill for discovery, authentication checks, wrapper generation, and approval-gated install guidance
- `skills/website-to-api/assets/site-skill-template/` - Templates bundled with the installed skill
- `skills/website-to-api/references/` - Progressive-disclosure guidance for HAR handling, auth/replay, and advanced API patterns
- `skills/website-to-api/scripts/analyze_har.py` - Redacted HAR-to-discovery report analyzer
- `skills/website-to-api/scripts/capture_har.py` - Optional sanitized local/CDP HAR capture
- `skills/website-to-api/scripts/install_site_skill.py` - Installer for generated site skills after user approval
- `templates/` - Repo-development copies of the generated site-skill templates
- `tests/` - Behavioral regression tests for deterministic helpers and install safety

## Generated Site Skill Flow

1. Use the `website-to-api` meta-skill to discover the API.
2. Once enough API information exists, use `$skill-creator` to create or update the site-specific skill.
3. Generate the skill first in `outputs/<site-name>-skill/`.
4. Validate the generated skill and run its client with `uv run outputs/<site-name>-skill/scripts/client.py --help`.
5. Ask the user before installing the generated skill.
6. If approved, run:

   ```bash
   uv run skills/website-to-api/scripts/install_site_skill.py outputs/<site-name>-skill --approved-by-user
   ```

7. Installed skills live at `${CODEX_HOME:-$HOME/.codex}/skills/<site-name>` and may be discovered by new Codex threads after the skill list refreshes.

Generated skills must not include `README.md`, `AGENTS.md`, changelogs, installation guides, quick references, browser state, cookies, logs, or other auxiliary files.

Generated website-to-api skills must set `policy.allow_implicit_invocation: false` in `agents/openai.yaml`.

## Python

- Use `uv run` for generated site client scripts.
- Use Codex's bundled Python for local validation/helper scripts when available:
  `/Users/vedmani/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3`

## Browser Automation

- Prefer `agent-browser` with a dedicated profile at `$HOME/.agent-browser/profiles/website-to-api` when CDP/network/cookie capabilities are useful.
- Use `--headed` for first-time login, SSO/2FA, consent screens, streamed UI inspection, and debugging.
- Use headless mode only for repeatable checks after the profile is already authenticated.
- Close `agent-browser` sessions when work is complete; close named sessions explicitly.
- Verify cleanup with `agent-browser session list`.
- Do not point automation at a live personal Chrome/Brave profile unless the user explicitly asks for CDP attachment.

## HAR Workflow

- Prefer a supplied or manually exported HAR as the safest discovery intake, ideally from a fresh isolated/incognito session.
- Do not make HAR import a capability gate: use live browser inspection when manual export is impractical or the user asks Codex to perform discovery.
- Keep automated local/CDP capture optional; use it only when requested or when repeatability or complete network history materially helps.
- Never print credential values. Reports omit non-secret examples unless explicitly requested.
- Treat arbitrary response bodies as potentially personal even after credential redaction.
- Never delete or rewrite a HAR supplied by the user.

## Templates and Installation

- Treat `skills/website-to-api/assets/site-skill-template/` as canonical and keep `templates/site-skill-template/` identical.
- Validate generated skills before touching an existing destination.
- Install through an atomic staged swap and restore the previous destination on failure.
- Reject HARs, environment files, browser state, credentials, unresolved placeholders, and auxiliary docs.

## Regression Testing

Run the local behavioral suite before a clean forward test. Ask the test agent to use the skill naturally on a benign artifact or public read-only workflow without revealing the intended implementation details.

## Security

Never commit auth tokens, cookie values, browser state, or credentials. All auth is via environment variables.
