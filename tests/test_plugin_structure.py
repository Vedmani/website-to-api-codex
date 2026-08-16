import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "website-to-api"
CANONICAL_TEMPLATE = SKILL / "assets" / "site-skill-template"
DEVELOPMENT_TEMPLATE = ROOT / "templates" / "site-skill-template"


def test_template_trees_are_identical():
    canonical_files = {
        path.relative_to(CANONICAL_TEMPLATE): path.read_bytes()
        for path in CANONICAL_TEMPLATE.rglob("*")
        if path.is_file()
    }
    development_files = {
        path.relative_to(DEVELOPMENT_TEMPLATE): path.read_bytes()
        for path in DEVELOPMENT_TEMPLATE.rglob("*")
        if path.is_file()
    }
    assert development_files == canonical_files


def test_core_skill_uses_progressive_disclosure():
    text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) < 200
    for reference in ("capture-and-har.md", "auth-and-replay.md", "api-patterns.md"):
        assert reference in text
        assert (SKILL / "references" / reference).is_file()


def test_client_template_avoids_secret_cli_flags_and_hardcoded_ua():
    text = (CANONICAL_TEMPLATE / "scripts" / "client.py.template").read_text(
        encoding="utf-8"
    )
    assert "website-to-api/1.0" not in text
    assert "cookie: Optional" not in text
    assert 'USER_AGENT_ENV = "SITE_UPPER_USER_AGENT"' in text
    assert "rendered = rendered[:1000]" in text
    assert "non-JSON response body omitted" in text
    assert "@app.callback()" in text


def test_manifest_matches_plugin_name_and_has_no_todos():
    manifest_path = ROOT / ".codex-plugin" / "plugin.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["name"] == SKILL.name
    assert manifest["repository"] == "https://github.com/Vedmani/website-to-api-codex"
    assert manifest["interface"]["developerName"] == "Vedmani"
    assert "[TODO:" not in manifest_path.read_text(encoding="utf-8")


def test_public_docs_do_not_contain_machine_specific_paths():
    for name in ("README.md", "AGENTS.md"):
        assert "/Users/" not in (ROOT / name).read_text(encoding="utf-8")
