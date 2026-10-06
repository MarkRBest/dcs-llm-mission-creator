"""Player-aircraft choices shared by the command line and mission builders."""

from __future__ import annotations

from enum import StrEnum

from dcs import planes
from dcs.unittype import FlyingType


class PlayerAircraft(StrEnum):
    """The flyable types a mission may offer as its client aircraft."""

    F_16C = "f16"
    FA_18C = "f18"

    @property
    def display_name(self) -> str:
        """The name used in player-facing mission text."""
        return "F-16C-50" if self is PlayerAircraft.F_16C else "F/A-18C"

    @property
    def unit_type(self) -> type[FlyingType]:
        """The pydcs aircraft class used to create a client flight."""
        return planes.F_16C_50 if self is PlayerAircraft.F_16C else planes.FA_18C_hornet
