#!/usr/bin/env python3
"""Validate every release version surface against pyproject.toml."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def _read_project_version(root: Path) -> str:
    """Read the project version from the [project] section of pyproject.toml."""
    in_project_section = False
    for line in (root / "pyproject.toml").read_text(encoding="utf-8").splitlines():
        stripped_line = line.strip()
        if stripped_line.startswith("["):
            in_project_section = stripped_line == "[project]"
            continue
        if in_project_section and stripped_line.startswith("version"):
            key, separator, value = stripped_line.partition("=")
            if key.strip() == "version" and separator:
                return value.strip().strip('"').strip("'")
    raise ValueError("Could not find project version in pyproject.toml")


def _read_json_version(path: Path) -> str:
    return str(json.loads(path.read_text(encoding="utf-8"))["version"])


def _read_lockfile_versions(path: Path) -> dict[str, str]:
    lockfile = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(path.relative_to(path.parents[1])): str(lockfile["version"]),
        f"{path.relative_to(path.parents[1])} packages[''].version": str(
            lockfile["packages"][""]["version"]
        ),
    }


def _read_uv_lock_version(path: Path) -> str:
    match = re.search(
        r'^\[\[package\]\]\s*\nname = "the-ai-counsel"\s*\nversion = "([^"]+)"',
        path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if not match:
        raise ValueError(f"Could not find the-ai-counsel package version in {path}")
    return match.group(1)


def _read_sidebar_version(path: Path) -> str:
    match = re.search(
        r'className=["\']sidebar-version["\']>\s*v([^<\s]+)',
        path.read_text(encoding="utf-8"),
    )
    if not match:
        raise ValueError(f"Could not find sidebar version in {path}")
    return match.group(1)


def _read_skill_version(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    frontmatter = text.split("---", 2)
    if len(frontmatter) < 3:
        raise ValueError(f"Could not find skill frontmatter in {path}")
    match = re.search(r"^version:\s*([^\s]+)\s*$", frontmatter[1], re.MULTILINE)
    if not match:
        raise ValueError(f"Could not find skill version in {path}")
    return match.group(1)


def _read_changelog_version(path: Path) -> str:
    match = re.search(
        r"^## \[([^\]]+)\] - \d{4}-\d{2}-\d{2}\s*$",
        path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if not match:
        raise ValueError(f"Could not find a dated release section in {path}")
    return match.group(1)


def _read_runtime_version(root: Path) -> str | None:
    """Read the MCP package version when checking the actual project root."""
    if (root / "the_ai_counsel_mcp").is_dir():
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from the_ai_counsel_mcp import __version__

        return __version__
    return None


def collect_versions(root: Path) -> dict[str, str]:
    """Collect all release-facing version values from a project root."""
    frontend = root / "frontend"
    versions = {
        "pyproject.toml": _read_project_version(root),
        "uv.lock": _read_uv_lock_version(root / "uv.lock"),
        "frontend/package.json": _read_json_version(frontend / "package.json"),
        "frontend/src/components/Sidebar.jsx": _read_sidebar_version(
            frontend / "src/components/Sidebar.jsx"
        ),
        "skills/the-ai-counsel-api/SKILL.md": _read_skill_version(
            root / "skills/the-ai-counsel-api/SKILL.md"
        ),
        "CHANGELOG.md": _read_changelog_version(root / "CHANGELOG.md"),
    }
    versions.update(
        _read_lockfile_versions(frontend / "package-lock.json")
    )
    runtime_version = _read_runtime_version(root)
    if runtime_version is not None:
        versions["the_ai_counsel_mcp.__version__"] = runtime_version
    return versions


def check_version_consistency(root: Path) -> list[str]:
    """Return human-readable errors for mismatched or malformed versions."""
    try:
        versions = collect_versions(root)
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return [str(exc)]

    expected = versions["pyproject.toml"]
    errors: list[str] = []
    if not VERSION_PATTERN.fullmatch(expected):
        errors.append(f"pyproject.toml: invalid semantic version {expected}")

    for surface, actual in versions.items():
        if actual != expected:
            errors.append(f"{surface}: expected {expected}, found {actual}")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    errors = check_version_consistency(root)
    if errors:
        print("Version consistency check failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Version consistency check passed: {_read_project_version(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
