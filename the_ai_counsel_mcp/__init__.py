"""The AI Counsel MCP Server."""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _get_version() -> str:
    """Read the app version from installed metadata or the source project file."""
    try:
        return version("the-ai-counsel")
    except PackageNotFoundError:
        pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
        in_project_section = False
        for line in pyproject_path.read_text(encoding="utf-8").splitlines():
            stripped_line = line.strip()
            if stripped_line.startswith("["):
                in_project_section = stripped_line == "[project]"
                continue
            if in_project_section and stripped_line.startswith("version"):
                key, separator, value = stripped_line.partition("=")
                if key.strip() == "version" and separator:
                    return value.strip().strip('"').strip("'")
        raise RuntimeError(f"Could not find the project version in {pyproject_path}")


__version__ = _get_version()
