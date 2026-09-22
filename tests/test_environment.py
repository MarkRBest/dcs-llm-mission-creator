"""Tests for project-local environment loading."""

from __future__ import annotations

import os
from pathlib import Path

from dcs_mission_creator import load_project_environment


def test_project_environment_loads_dotenv_values(tmp_path: Path, monkeypatch) -> None:
    """A local .env makes its values available to the generator."""
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("DCS_INSTALL_DIR=/tmp/dcs-world\n")
    monkeypatch.delenv("DCS_INSTALL_DIR", raising=False)

    assert load_project_environment(dotenv_path)
    assert os.environ["DCS_INSTALL_DIR"] == "/tmp/dcs-world"


def test_shell_environment_takes_precedence(tmp_path: Path, monkeypatch) -> None:
    """An explicit shell setting is never silently replaced by .env."""
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("DCS_INSTALL_DIR=/tmp/from-dotenv\n")
    monkeypatch.setenv("DCS_INSTALL_DIR", "/tmp/from-shell")

    load_project_environment(dotenv_path)

    assert os.environ["DCS_INSTALL_DIR"] == "/tmp/from-shell"
