#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml>=6"]
# ///
"""Validate and atomically install a generated site skill after user approval."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

DISALLOWED_DOCS = {
    "agents.md",
    "changelog.md",
    "installation-guide.md",
    "installation_guide.md",
    "quick-reference.md",
    "quick_reference.md",
    "readme.md",
}
SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "logs",
    "node_modules",
    "outputs",
    "work",
}
SENSITIVE_SUFFIXES = {
    ".auth-state.json",
    ".cookies",
    ".cookies.txt",
    ".har",
    ".key",
    ".log",
    ".p12",
    ".pem",
    ".pyc",
    ".pyo",
}
SENSITIVE_NAME_PARTS = (
    "auth-state",
    "auth_state",
    "cookie",
    "credential",
    "secret",
    "session",
    "storage-state",
    "storage_state",
    "token",
)
PLACEHOLDER_PATTERNS = (
    re.compile(r"\bSITE_[A-Z0-9_]+\b"),
    re.compile(
        r"\b(?:YES_OR_NO|GET_OR_POST|COOKIE_OR_HEADER_NAMES|COOKIE_NAME_OR_EMPTY)\b"
    ),
    re.compile(r"\bYYYY-MM-DD\b"),
    re.compile(r"\b(?:TODO|FIXME)(?::|\b)"),
)


def default_skills_root() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser() / "skills"
    return Path.home() / ".codex" / "skills"


def normalize_skill_name(value: str) -> str:
    name = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    name = re.sub(r"-+", "-", name)
    if not name:
        raise ValueError("skill name cannot be empty after normalization")
    if len(name) > 63:
        name = name[:63].rstrip("-")
    return name


def read_frontmatter_name(skill_dir: Path) -> Optional[str]:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None
    in_frontmatter = False
    for line in skill_md.read_text(encoding="utf-8").splitlines():
        if line.strip() == "---":
            if not in_frontmatter:
                in_frontmatter = True
                continue
            break
        if in_frontmatter and line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return None


def find_disallowed_docs(skill_dir: Path) -> List[Path]:
    return [
        path.relative_to(skill_dir)
        for path in skill_dir.rglob("*")
        if path.is_file() and path.name.lower() in DISALLOWED_DOCS
    ]


def is_sensitive_path(path: Path) -> bool:
    lower = path.name.lower()
    if lower == ".env" or lower.startswith(".env."):
        return True
    if any(lower.endswith(suffix) for suffix in SENSITIVE_SUFFIXES):
        return True
    return any(part in lower for part in SENSITIVE_NAME_PARTS)


def find_sensitive_artifacts(skill_dir: Path) -> List[Path]:
    found: List[Path] = []
    for path in skill_dir.rglob("*"):
        relative = path.relative_to(skill_dir)
        if any(part.lower() in SKIP_DIRS for part in relative.parts[:-1]):
            continue
        if path.is_file() and is_sensitive_path(path):
            found.append(relative)
    return found


def find_symlinks(skill_dir: Path) -> List[Path]:
    return [
        path.relative_to(skill_dir)
        for path in skill_dir.rglob("*")
        if path.is_symlink()
    ]


def should_skip(path_name: str, is_dir: bool) -> bool:
    lower = path_name.lower()
    if is_dir and lower in SKIP_DIRS:
        return True
    return is_sensitive_path(Path(path_name))


def ignore_names(directory: str, names: Iterable[str]) -> List[str]:
    base = Path(directory)
    return [name for name in names if should_skip(name, (base / name).is_dir())]


def find_placeholders(skill_dir: Path) -> List[str]:
    found: List[str] = []
    for path in skill_dir.rglob("*"):
        if not path.is_file() or should_skip(path.name, False):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in PLACEHOLDER_PATTERNS:
            match = pattern.search(text)
            if match:
                found.append(f"{path.relative_to(skill_dir)}:{match.group(0)}")
    return found


def quick_validate_path() -> Path:
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    return (
        codex_home
        / "skills"
        / ".system"
        / "skill-creator"
        / "scripts"
        / "quick_validate.py"
    )


def run_validation(skill_dir: Path, validator: Path) -> None:
    if not validator.exists():
        raise FileNotFoundError(f"quick_validate.py not found at {validator}")
    subprocess.run([sys.executable, str(validator), str(skill_dir)], check=True)


def preflight(skill_dir: Path, validator: Path, skip_validate: bool) -> None:
    if not skill_dir.is_dir():
        raise NotADirectoryError(f"source skill directory not found: {skill_dir}")
    if not (skill_dir / "SKILL.md").is_file():
        raise FileNotFoundError(f"source is missing SKILL.md: {skill_dir}")
    if not (skill_dir / "agents" / "openai.yaml").is_file():
        raise FileNotFoundError(
            "source is missing agents/openai.yaml; use $skill-creator first"
        )

    disallowed = find_disallowed_docs(skill_dir)
    if disallowed:
        raise ValueError(
            "generated skills must not include auxiliary docs: "
            + ", ".join(str(path) for path in disallowed)
        )
    sensitive = find_sensitive_artifacts(skill_dir)
    if sensitive:
        raise ValueError(
            "generated skill contains secret-like artifacts: "
            + ", ".join(str(path) for path in sensitive)
        )
    symlinks = find_symlinks(skill_dir)
    if symlinks:
        raise ValueError(
            "generated skills must not contain symbolic links: "
            + ", ".join(str(path) for path in symlinks)
        )
    placeholders = find_placeholders(skill_dir)
    if placeholders:
        raise ValueError(
            "generated skill contains unresolved placeholders: "
            + ", ".join(placeholders)
        )
    if not skip_validate:
        run_validation(skill_dir, validator)


def atomic_install(
    source: Path, destination: Path, validator: Path, skip_validate: bool, force: bool
) -> None:
    destination_root = destination.parent
    destination_root.mkdir(parents=True, exist_ok=True)
    stage_root = Path(
        tempfile.mkdtemp(prefix=f".{destination.name}-stage-", dir=destination_root)
    )
    staged = stage_root / destination.name
    backup = stage_root / f"{destination.name}.previous"
    replaced = False
    cleanup_stage = True
    try:
        shutil.copytree(source, staged, ignore=ignore_names)
        if not skip_validate:
            run_validation(staged, validator)
        if destination.exists():
            if not force:
                raise FileExistsError(
                    f"destination already exists; use --force to replace: {destination}"
                )
            os.replace(destination, backup)
            replaced = True
        os.replace(staged, destination)
    except Exception:
        if replaced and backup.exists() and not destination.exists():
            try:
                os.replace(backup, destination)
            except Exception as restore_error:
                cleanup_stage = False
                raise RuntimeError(
                    "installation and automatic restore both failed; "
                    f"the previous skill is preserved at {backup}"
                ) from restore_error
        raise
    finally:
        if cleanup_stage:
            shutil.rmtree(stage_root, ignore_errors=True)


def install_skill(args: argparse.Namespace) -> int:
    source = Path(args.source).expanduser().resolve()
    validator = Path(args.validator).expanduser().resolve()
    preflight(source, validator, args.skip_validate)

    raw_name = args.name or read_frontmatter_name(source) or source.name
    skill_name = normalize_skill_name(raw_name)
    destination_root = Path(args.destination_root).expanduser().resolve()
    destination = destination_root / skill_name

    if args.dry_run:
        print(f"[dry-run] Validated source: {source}")
        print(f"[dry-run] Would atomically install to: {destination}")
        print(
            "[dry-run] Secret-like artifacts, HARs, environment files, caches, and logs are rejected"
        )
        return 0

    if not args.approved_by_user:
        raise PermissionError(
            "installation requires explicit user approval; rerun with --approved-by-user"
        )

    atomic_install(source, destination, validator, args.skip_validate, args.force)
    print(f"Installed {skill_name} to {destination}")
    print("New Codex threads should discover the skill after the skill list refreshes.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and atomically install a generated website API skill."
    )
    parser.add_argument("source", help="Generated site skill directory")
    parser.add_argument("--name", help="Override installed skill name")
    parser.add_argument(
        "--destination-root",
        default=str(default_skills_root()),
        help="Skills root; defaults to ${CODEX_HOME:-$HOME/.codex}/skills",
    )
    parser.add_argument(
        "--validator",
        default=str(quick_validate_path()),
        help="Path to skill-creator quick_validate.py",
    )
    parser.add_argument(
        "--force", action="store_true", help="Replace an existing installed skill"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and show the installation target",
    )
    parser.add_argument(
        "--skip-validate", action="store_true", help="Skip quick_validate.py"
    )
    parser.add_argument(
        "--approved-by-user",
        action="store_true",
        help="Required confirmation that the user approved installation",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return install_skill(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
