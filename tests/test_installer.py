import argparse
import importlib.util
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER_PATH = (
    ROOT / "skills" / "website-to-api" / "scripts" / "install_site_skill.py"
)


def load_installer():
    spec = importlib.util.spec_from_file_location(
        "website_to_api_installer", INSTALLER_PATH
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


installer = load_installer()


def make_skill(root: Path, name: str = "example-api") -> Path:
    root.mkdir(parents=True)
    (root / "agents").mkdir()
    (root / "scripts").mkdir()
    (root / "SKILL.md").write_text(
        f'---\nname: {name}\ndescription: "Use the verified example API."\n---\n\n# Example\n',
        encoding="utf-8",
    )
    (root / "agents" / "openai.yaml").write_text(
        'interface:\n  display_name: "Example"\npolicy:\n  allow_implicit_invocation: false\n',
        encoding="utf-8",
    )
    (root / "scripts" / "client.py").write_text("print('new')\n", encoding="utf-8")
    return root


def test_preflight_rejects_sensitive_artifacts_and_placeholders(tmp_path):
    skill = make_skill(tmp_path / "skill")
    (skill / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    with pytest.raises(ValueError, match="secret-like artifacts"):
        installer.preflight(skill, tmp_path / "validator.py", skip_validate=True)
    (skill / ".env").unlink()
    (skill / "SKILL.md").write_text("SITE_API_BASE\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unresolved placeholders"):
        installer.preflight(skill, tmp_path / "validator.py", skip_validate=True)
    (skill / "SKILL.md").write_text("# TODO: implement parser\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unresolved placeholders"):
        installer.preflight(skill, tmp_path / "validator.py", skip_validate=True)


def test_preflight_rejects_symbolic_links(tmp_path):
    skill = make_skill(tmp_path / "skill")
    outside = tmp_path / "outside.txt"
    outside.write_text("do not copy\n", encoding="utf-8")
    (skill / "scripts" / "linked.txt").symlink_to(outside)
    with pytest.raises(ValueError, match="symbolic links"):
        installer.preflight(skill, tmp_path / "validator.py", skip_validate=True)


def test_atomic_install_replaces_only_after_staging(tmp_path):
    source = make_skill(tmp_path / "source")
    destination = make_skill(tmp_path / "installed")
    (destination / "scripts" / "client.py").write_text(
        "print('old')\n", encoding="utf-8"
    )

    installer.atomic_install(
        source,
        destination,
        tmp_path / "validator.py",
        skip_validate=True,
        force=True,
    )
    assert (destination / "scripts" / "client.py").read_text(
        encoding="utf-8"
    ) == "print('new')\n"


def test_atomic_install_restores_previous_destination_on_swap_failure(
    tmp_path, monkeypatch
):
    source = make_skill(tmp_path / "source")
    destination = make_skill(tmp_path / "installed")
    old_client = destination / "scripts" / "client.py"
    old_client.write_text("print('old')\n", encoding="utf-8")
    real_replace = os.replace
    calls = 0

    def failing_replace(src, dst):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated swap failure")
        return real_replace(src, dst)

    monkeypatch.setattr(installer.os, "replace", failing_replace)
    with pytest.raises(OSError, match="simulated"):
        installer.atomic_install(
            source,
            destination,
            tmp_path / "validator.py",
            skip_validate=True,
            force=True,
        )
    assert old_client.read_text(encoding="utf-8") == "print('old')\n"


def test_atomic_install_preserves_backup_when_restore_also_fails(tmp_path, monkeypatch):
    source = make_skill(tmp_path / "source")
    destination = make_skill(tmp_path / "installed")
    (destination / "scripts" / "client.py").write_text(
        "print('old')\n", encoding="utf-8"
    )
    real_replace = os.replace
    calls = 0

    def failing_replace(src, dst):
        nonlocal calls
        calls += 1
        if calls in {2, 3}:
            raise OSError("simulated swap or restore failure")
        return real_replace(src, dst)

    monkeypatch.setattr(installer.os, "replace", failing_replace)
    with pytest.raises(RuntimeError, match="previous skill is preserved"):
        installer.atomic_install(
            source,
            destination,
            tmp_path / "validator.py",
            skip_validate=True,
            force=True,
        )
    backups = list(tmp_path.glob(".installed-stage-*/installed.previous"))
    assert len(backups) == 1
    assert (backups[0] / "scripts" / "client.py").read_text(
        encoding="utf-8"
    ) == "print('old')\n"


def test_dry_run_does_not_mutate_destination(tmp_path, capsys):
    source = make_skill(tmp_path / "source")
    destination_root = tmp_path / "skills"
    args = argparse.Namespace(
        source=str(source),
        validator=str(tmp_path / "validator.py"),
        skip_validate=True,
        name=None,
        destination_root=str(destination_root),
        approved_by_user=False,
        dry_run=True,
        force=False,
    )
    assert installer.install_skill(args) == 0
    assert not destination_root.exists()
    assert "Would atomically install" in capsys.readouterr().out
