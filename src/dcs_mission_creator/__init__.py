"""DCS mission creator package."""

from pathlib import Path

from dotenv import load_dotenv


def load_project_environment(dotenv_path: Path | None = None) -> bool:
    """Load the repository's ``.env`` without replacing shell configuration."""
    path = dotenv_path or Path(__file__).resolve().parents[2] / ".env"
    return load_dotenv(path, override=False)


# The package initialises before the CLI module, so DCS_INSTALL_DIR and related
# settings are available before mission discovery or generation begins.
load_project_environment()

__all__ = []
