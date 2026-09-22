"""Map a mission builder's package location to an output directory path."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dcs_mission_creator.core.mission_builder import MissionBuilder

_MISSIONS_PREFIX = "dcs_mission_creator.missions."


def output_relative_path(builder: type[MissionBuilder]) -> Path:
    """Return the mission module path relative to ``missions``.

    For example, ``missions.afghanistan.cap.kabul_patrol`` becomes
    ``afghanistan/cap/kabul_patrol``.  Keeping generated artefacts in the same
    hierarchy makes a large mission library navigable without changing stable
    CLI slugs.
    """
    module = builder.__module__
    if not module.startswith(_MISSIONS_PREFIX):
        raise ValueError(f"mission builder is outside {_MISSIONS_PREFIX}: {module}")
    return Path(*module.removeprefix(_MISSIONS_PREFIX).split("."))
