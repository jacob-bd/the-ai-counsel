"""Tests for the release version consistency check."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.check_version_consistency import check_version_consistency


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _write_version_fixture(root: Path, version: str, *, package_version: str | None = None) -> None:
    frontend = root / "frontend"
    frontend.mkdir(parents=True)
    package_version = package_version or version

    (root / "pyproject.toml").write_text(
        f"[project]\nversion = \"{version}\"\n",
        encoding="utf-8",
    )
    (root / "uv.lock").write_text(
        f'[[package]]\nname = "the-ai-counsel"\nversion = "{version}"\n',
        encoding="utf-8",
    )
    (frontend / "package.json").write_text(
        json.dumps({"version": package_version}),
        encoding="utf-8",
    )
    (frontend / "package-lock.json").write_text(
        json.dumps({"version": version, "packages": {"": {"version": version}}}),
        encoding="utf-8",
    )
    (frontend / "src").mkdir()
    (frontend / "src/components").mkdir()
    (frontend / "src/components/Sidebar.jsx").write_text(
        f'<div className="sidebar-version">v{version}</div>',
        encoding="utf-8",
    )
    (root / "skills").mkdir()
    (root / "skills/the-ai-counsel-api").mkdir()
    (root / "skills/the-ai-counsel-api/SKILL.md").write_text(
        f"---\nversion: {version}\n---\n",
        encoding="utf-8",
    )
    (root / "CHANGELOG.md").write_text(
        f"## [Unreleased]\n\n## [{version}] - 2026-08-02\n",
        encoding="utf-8",
    )


def test_current_release_surfaces_are_consistent():
    assert check_version_consistency(PROJECT_ROOT) == []


def test_checker_reports_a_stale_release_surface(tmp_path):
    _write_version_fixture(tmp_path, "0.11.2", package_version="0.11.1")

    errors = check_version_consistency(tmp_path)

    assert errors == [
        "frontend/package.json: expected 0.11.2, found 0.11.1",
    ]
