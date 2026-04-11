# website-to-api

## Overview

Claude Code plugin for reverse-engineering website internal APIs using Chrome browser automation.

## Structure

- `skills/website-to-api/` — Meta-skill: the discovery and wrapping pattern
- `skills/substack/` — Substack-specific implementation
- `templates/` — Starter files for adding new sites (not auto-discovered as skills)

## Adding a New Site Skill

1. Copy `templates/site-skill-template/` to `skills/<site-name>/`
2. Use the `website-to-api` meta-skill to discover the API
3. Fill in the SKILL.md template placeholders and implement the script
4. Test with `uv run skills/<site-name>/scripts/client.py --help`

## Security

Never commit auth tokens, cookie values, or credentials. All auth is via environment variables.
