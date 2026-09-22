"""Tests for generated mission output hierarchy."""

from __future__ import annotations

from pathlib import Path

from dcs_mission_creator.__main__ import _cmd_generate, _default_output_dir
from dcs_mission_creator.core.mission_paths import output_relative_path
from dcs_mission_creator.missions.caucasus.coastal_cover import CoastalCover


class _NestedAfghanistanMission:
    """A representative mission nested below a theatre package."""

    __module__ = "dcs_mission_creator.missions.afghanistan.cap.kabul_patrol"
    name = "kabul_patrol"


def test_output_relative_path_follows_the_mission_package() -> None:
    """Nested mission packages become nested generated-mission folders."""
    assert output_relative_path(_NestedAfghanistanMission) == Path(
        "afghanistan/cap/kabul_patrol"
    )


def test_default_output_dir_follows_the_mission_package(monkeypatch) -> None:
    """The DCS Missions output keeps the terrain package in its path."""
    monkeypatch.setenv("DCS_MISSIONS_FOLDER", "/tmp/DCS/Missions")

    assert _default_output_dir(CoastalCover) == Path(
        "/tmp/DCS/Missions/IAGeneratedMissions/caucasus/coastal_cover"
    )


def test_generate_all_preserves_the_mission_package(
    tmp_path: Path, monkeypatch
) -> None:
    """A custom root still receives one tree that mirrors source packages."""
    recorded: list[Path] = []
    monkeypatch.setattr(
        "dcs_mission_creator.__main__._generate_one",
        lambda slug, cls, target, players: recorded.append(target),
    )

    assert (
        _cmd_generate({"coastal_cover": CoastalCover}, None, tmp_path, players=2) == 0
    )
    assert recorded == [tmp_path / "caucasus/coastal_cover"]
