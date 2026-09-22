"""Afghanistan ``Bagram Cave Strike`` — a short hot-start Hornet sortie.

The player launches hot from Bagram in an F/A-18C, climbs north-east into the
Panjshir foothills, and destroys a cave entrance represented by DCS's hardened
fire-control bunker object.  The small guard detachment has a Strela-10, two
ZU-23 emplacements, and MANPADS: enough to make a high Paveway attack and a
clean egress matter, without turning a first Afghanistan mission into a SEAD
campaign.
"""

from __future__ import annotations

from datetime import datetime, timezone

from dcs import planes, statics, task, vehicles
from dcs.country import Country
from dcs.mission import Mission, StartType
from dcs.terrain.afghanistan.afghanistan import Afghanistan
from dcs.terrain.terrain import Airport
from dcs.unit import Skill
from dcs.unitgroup import FlyingGroup, VehicleGroup

from dcs_mission_creator.core.cli import run_cli
from dcs_mission_creator.core.difficulty import Difficulty
from dcs_mission_creator.core.loadout import Loadout
from dcs_mission_creator.core.map_draw import PlanOverlay
from dcs_mission_creator.core.mission_builder import Assembled, MissionBuilder
from dcs_mission_creator.core.mission_kit import offset, player_flight, set_skill
from dcs_mission_creator.core.placement import load_scene
from dcs_mission_creator.core.weather import Weather, Wind

# The Panjshir-side ridge north-east of Bagram.  Positions are expressed as
# latitude/longitude and converted by MissionBuilder.at(), rather than copied
# map metres, so the intended geography remains reviewable.
_CAVE_LAT = 35.3000
_CAVE_LON = 69.4500
_CLIMB_ALTITUDE_M = 5_500
_ATTACK_ALTITUDE_M = 5_000
_CRUISE_SPEED_KPH = 760

# Four Paveways are enough for the hardened cave entrance and leave a second
# pair for a re-attack.  The ATFLIR is on station 4; the player self-designates
# using the Hornet's usual default laser code, 1688.
_HORNET_FIT = Loadout(
    role="GBU-12 / ATFLIR",
    carries=(
        "four GBU-12 Paveways on BRU-33 racks, ATFLIR, one 330 gal tank, "
        "two AIM-9X and one AIM-120C"
    ),
    stores=(
        (1, "AIM_9X_Sidewinder_IR_AAM"),
        (3, "BRU_33_with_2_x_GBU_12___500lb_Laser_Guided_Bomb"),
        (4, "AN_ASQ_228_ATFLIR___Targeting_Pod"),
        (5, "FPU_8A_Fuel_Tank_330_gallons"),
        (6, "AIM_120C_AMRAAM___Active_Radar_AAM"),
        (7, "BRU_33_with_2_x_GBU_12___500lb_Laser_Guided_Bomb"),
        (9, "AIM_9X_Sidewinder_IR_AAM"),
    ),
)
# This is a training sortie, not a split-package strike: both selectable Hornet
# slots receive the same self-contained Paveway fit deliberately.
_HORNET_FITS = (_HORNET_FIT, _HORNET_FIT)


class BagramCaveStrike(MissionBuilder):
    """A deliberately small, flyable first mission for the Afghanistan map."""

    name = "bagram_cave_strike"
    title = "Bagram Cave Strike"
    difficulty = Difficulty.RECRUIT
    terrain = Afghanistan
    blue_task = (
        "Launch hot from Bagram, strike the Panjshir cave entrance with "
        "GBU-12s, avoid the short-range defences, and recover at Bagram."
    )
    red_task = (
        "Protect the Panjshir cave entrance with the local Strela, AAA, and "
        "MANPADS section."
    )
    start_time = datetime(2026, 10, 18, 9, 30, tzinfo=timezone.utc)
    weather = Weather(
        name="Clear Panjshir morning",
        season_temperature=18,
        clouds_base=4_000,
        clouds_thickness=400,
        clouds_density=1,
        visibility_distance=50_000,
        wind_at_ground=Wind(direction=310, speed=3),
        wind_at_2000=Wind(direction=320, speed=7),
        wind_at_8000=Wind(direction=330, speed=13),
    )

    def _assemble(self, m: Mission, plan: PlanOverlay) -> Assembled:
        bagram = self._terrain.airports["Bagram"]
        bagram.set_blue()
        cave = self.at(_CAVE_LAT, _CAVE_LON)
        scene = load_scene("afghanistan")

        m.static_group(
            m.country("Russia"),
            "Panjshir cave entrance",
            statics.Fortification.Fire_Control_Bunker,
            position=cave,
            heading=225,
        )
        self._spawn_defences(m, m.country("Russia"), cave)

        usa = m.country("USA")
        for hornet in player_flight(
            m,
            country=usa,
            name="Razor",
            aircraft_type=planes.FA_18C_hornet,
            airport=bagram,
            maintask=task.CAS,
            # pydcs calls a running aircraft on the parking ramp "Warm".
            start_type=StartType.Warm,
            slots=self.players,
            loadouts=_HORNET_FITS,
        ):
            self._route(hornet, bagram, cave)

        plan.route((bagram.position, cave), label="BAGRAM → PANJSHIR")
        plan.objective(cave, "CAVE ENTRANCE", radius=2_500)
        plan.threat(
            offset(cave, east_m=1_600, north_m=1_100),
            radius=5_000,
            label="SA-13",
        )
        plan.threat(
            offset(cave, east_m=-650, north_m=450),
            radius=2_500,
            label="AAA",
        )
        return Assembled(scene.overlay)

    def _spawn_defences(self, m: Mission, russia: Country, cave) -> None:
        """Place a local, low-level threat rather than a theatre-wide SAM belt."""
        sa13 = m.vehicle_group(
            russia,
            "Panjshir SA-13",
            vehicles.AirDefence.Strela_10M3,
            position=offset(cave, east_m=1_600, north_m=1_100),
            heading=225,
        )
        aaa = m.vehicle_group(
            russia,
            "Panjshir AAA",
            vehicles.AirDefence.ZU_23_Emplacement,
            position=offset(cave, east_m=-650, north_m=450),
            heading=45,
            group_size=2,
            formation=VehicleGroup.Formation.Scattered,
        )
        manpads = m.vehicle_group(
            russia,
            "Panjshir MANPADS",
            vehicles.AirDefence.SA_18_Igla_manpad,
            position=offset(cave, east_m=300, north_m=-550),
            heading=45,
            group_size=3,
            formation=VehicleGroup.Formation.Scattered,
        )
        for group in (sa13, aaa, manpads):
            set_skill(group, Skill.Average)

    @staticmethod
    def _route(hornet: FlyingGroup, bagram: Airport, cave) -> None:
        """A short high ingress, deliberate attack point, and direct recovery."""
        hornet.add_runway_waypoint(bagram)
        hornet.add_waypoint(
            offset(cave, east_m=-8_000, north_m=-7_000),
            altitude=_CLIMB_ALTITUDE_M,
            speed=_CRUISE_SPEED_KPH,
            name="PUSH",
        )
        hornet.add_waypoint(
            cave,
            altitude=_ATTACK_ALTITUDE_M,
            speed=700,
            name="CAVE ATTACK",
        )
        hornet.add_waypoint(
            offset(cave, east_m=-10_000, north_m=-3_000),
            altitude=_CLIMB_ALTITUDE_M,
            speed=_CRUISE_SPEED_KPH,
            name="EGRESS",
        )
        hornet.add_runway_waypoint(bagram)
        hornet.land_at(bagram)

    def _in_game_briefing(self) -> str:
        return f"""BAGRAM CAVE STRIKE — Afghanistan, 18 October 2026, 09:30 local
===============================================================
MISSION
  Razor launches hot from Bagram and attacks a cave entrance on the
  Panjshir-side ridge, {round(self.at(_CAVE_LAT, _CAVE_LON).distance_to_point(self._terrain.airports["Bagram"].position) / 1000):.0f} km north-east of the field.
  The target is a hardened bunker object used as the cave entrance.

THREATS
  One SA-13, two ZU-23 emplacements, and a small SA-18 MANPADS section
  guard the entrance. They are short-range systems: remain high on the
  ingress, self-designate with the ATFLIR, release the Paveways, and egress.

LOADOUT
{self.loadout_brief("Razor", _HORNET_FITS)}
  GBU-12 default laser code: 1688. The aircraft are hot on Bagram's ramp.

ROUTE
  BAGRAM → PUSH → CAVE ATTACK → EGRESS → BAGRAM
  Attack altitude: {_ATTACK_ALTITUDE_M:,} m MSL. Recover at Bagram when the
  cave entrance is destroyed.
"""

    def readme(self) -> str:
        return f"""# {self.title}

## Mission

Launch **hot** from **Bagram** in an F/A-18C Hornet, climb north-east into the
Panjshir foothills, and destroy the hardened bunker that represents the cave
entrance. It is approximately **{round(self.at(_CAVE_LAT, _CAVE_LON).distance_to_point(self._terrain.airports["Bagram"].position) / 1000):.0f} km** from Bagram.

{self.slot_summary("Razor")}. Every slot is a hot-start Hornet:

{self.loadout_table("Razor", _HORNET_FITS)}

Use the ATFLIR to self-designate. GBU-12s use the Hornet's default laser code,
**1688**.

## Threats and route

The cave guard consists of one SA-13, two ZU-23 emplacements, and a small
SA-18 MANPADS section. They are deliberately short-range: stay high through
the **PUSH** point, attack from the published 5,000 m MSL point, then use the
**EGRESS** waypoint to turn back to Bagram.

```text
BAGRAM → PUSH → CAVE ATTACK → EGRESS → BAGRAM
```

## Re-generate

```bash
uv run dcs-mission-creator generate {self.name} --output-dir out/{self.name}
```
"""


def main() -> None:
    run_cli(BagramCaveStrike)


if __name__ == "__main__":
    main()
