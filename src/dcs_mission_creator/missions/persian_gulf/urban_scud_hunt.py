"""Persian Gulf ``Urban Scud Hunt`` — moving-target Maverick practice.

Razor launches from Khasab with one AI wingman to hunt two Iranian Scud-B
launchers circulating through central Bandar Abbas. The TELs are never parked:
DCS selects one of three starting sectors and directions, then sends the pair
around two laps of an urban road circuit. The six route anchors are road-snapped
inside the overlay's Bandar Abbas building return; their measured 500 m building
coverage runs from 76 percent to complete coverage. The circuit measures 8.1 km
before DCS road pathing, so two laps at 20 km/h outlast the forty-minute launch
window even on the straight-line lower bound.

Two groups of unarmed local traffic use the same streets in opposite directions.
They are not objectives and make positive identification part of the exercise.
Each Hornet carries four AGM-65F Mavericks, enough to prosecute both TELs and
still permit two training misses. The airborne MiG-23 response from ``scud_hunt``
is retained so the sortie remains a combat search rather than a sterile range.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from dcs import planes, task, vehicles
from dcs.country import Country
from dcs.mapping import Point
from dcs.mission import Mission, StartType
from dcs.point import PointAction
from dcs.terrain import PersianGulf
from dcs.terrain.terrain import Airport
from dcs.unit import Skill
from dcs.unitgroup import FlyingGroup, VehicleGroup

from dcs_mission_creator.core import loadout
from dcs_mission_creator.core.cli import run_cli
from dcs_mission_creator.core.difficulty import Difficulty
from dcs_mission_creator.core.loadout import Loadout
from dcs_mission_creator.core.map_draw import PlanOverlay
from dcs_mission_creator.core.mission_builder import Assembled
from dcs_mission_creator.core.mission_kit import offset, set_skill
from dcs_mission_creator.core.placement import convoy_spawn, load_scene
from dcs_mission_creator.core.weather import Weather, Wind
from dcs_mission_creator.map_overlay.scene import TacticalScene
from dcs_mission_creator.missions.persian_gulf.scud_hunt import (
    ScudHunt,
    _TargetOption,
)

_LAUNCH_WINDOW_MIN = 40
_CRUISE_ALTITUDE_M = 7_000
_CRUISE_SPEED_KPH = 760
_SCUD_SPEED_KPH = 20
_TRAFFIC_SPEED_KPH = 18

# Road points forming a clockwise circuit through central Bandar Abbas. Each
# point was selected from the Persian Gulf overlay's roads and buildings layers;
# `_urban_circuit` snaps them again at build time with built-up avoidance off.
_URBAN_CIRCUIT_ANCHORS = (
    (27.176097, 56.274647),
    (27.195458, 56.279857),
    (27.195637, 56.290196),
    (27.185888, 56.299677),
    (27.180790, 56.299903),
    (27.184773, 56.295077),
)

_HORNET_FIT = Loadout(
    role="AGM-65F*4",
    carries=(
        "four AGM-65F IR Mavericks, two AIM-120Cs, two AIM-9Ms, and one "
        "330-gallon centerline tank"
    ),
    stores=(
        (1, "AIM_9M_Sidewinder_IR_AAM"),
        (2, "LAU_117_AGM_65F"),
        (3, "LAU_117_AGM_65F"),
        (4, "AIM_120C_AMRAAM___Active_Radar_AAM"),
        (5, "FPU_8A_Fuel_Tank_330_gallons"),
        (6, "AIM_120C_AMRAAM___Active_Radar_AAM"),
        (7, "LAU_117_AGM_65F"),
        (8, "LAU_117_AGM_65F"),
        (9, "AIM_9M_Sidewinder_IR_AAM"),
    ),
)
_HORNET_FITS = (_HORNET_FIT, _HORNET_FIT)

_TRAFFIC_TYPES = (
    vehicles.Unarmed.VAZ_Car,
    vehicles.Unarmed.IKARUS_Bus,
    vehicles.Unarmed.Gaz_66_civil,
    vehicles.Unarmed.Zil_131_civil,
)


class UrbanScudHunt(ScudHunt):
    """A two-Hornet hunt for road-mobile TELs hidden in city traffic."""

    name = "urban_scud_hunt"
    title = "Urban Scud Hunt"
    ground_speed_kph = _SCUD_SPEED_KPH
    difficulty = Difficulty.TRAINED
    terrain = PersianGulf
    blue_task = (
        "Find and destroy both road-mobile Scud-B launchers circulating through "
        "central Bandar Abbas before their launch window closes. Positive "
        "identification is mandatory: unarmed buses, cars, and cargo trucks are "
        "using the same streets. Use AGM-65F Mavericks and avoid urban collateral."
    )
    red_task = (
        "Keep both Scud launchers moving through Bandar Abbas, use city traffic "
        "and buildings for concealment, and preserve them through the launch window."
    )
    start_time = datetime(2026, 10, 18, 10, 20, tzinfo=timezone.utc)
    weather = Weather(
        name="Clear Persian Gulf late morning",
        season_temperature=30,
        clouds_base=5_500,
        clouds_thickness=400,
        clouds_density=1,
        visibility_distance=45_000,
        wind_at_ground=Wind(direction=310, speed=3),
        wind_at_2000=Wind(direction=320, speed=7),
        wind_at_8000=Wind(direction=330, speed=12),
    )

    def __init__(self, *, players: int = 2) -> None:
        if players != 2:
            raise ValueError(
                "urban_scud_hunt is fixed at one player plus one AI wingman"
            )
        super().__init__(players=2)

    def _assemble(self, m: Mission, plan: PlanOverlay) -> Assembled:
        """Build the urban circuit, traffic, combat response, and Razor flight."""
        khasab = self._terrain.airports["Khasab"]
        bandar_abbas = self._terrain.airports["Bandar Abbas Intl"]
        khasab.set_blue()
        bandar_abbas.set_red()

        scene = load_scene("persiangulf")
        usa, iran = m.country("USA"), m.country("Iran")
        circuit = self._urban_circuit(scene)
        search_center = circuit[0].midpoint(circuit[3])

        razor = self._spawn_player(m, usa, khasab, search_center)
        targets = self._spawn_urban_targets(m, iran, circuit, search_center)
        self._spawn_city_traffic(m, iran, circuit)
        migs = self._spawn_intercept(m, iran, search_center)
        self._add_runtime_logic(m, razor, targets, migs)
        self._draw_plan(plan, khasab.position, search_center)
        return Assembled(scene.overlay)

    def _urban_circuit(self, scene: TacticalScene) -> tuple[Point, ...]:
        """Resolve six dense-city anchors onto Bandar Abbas roads."""
        return tuple(
            convoy_spawn(
                scene,
                self.at(lat, lng),
                radius_m=500,
                avoid_built_up=False,
            )
            for lat, lng in _URBAN_CIRCUIT_ANCHORS
        )

    @staticmethod
    def _patrol_route(
        circuit: Sequence[Point], *, start: int, clockwise: bool
    ) -> tuple[Point, ...]:
        """Return two complete laps from a chosen sector and direction."""
        direction = 1 if clockwise else -1
        return tuple(
            circuit[(start + direction * step) % len(circuit)]
            for step in range(2 * len(circuit) + 1)
        )

    def _spawn_urban_targets(
        self,
        m: Mission,
        iran: Country,
        circuit: Sequence[Point],
        search_center: Point,
    ) -> tuple[_TargetOption, ...]:
        """Build three runtime alternatives whose TELs are all road-mobile."""
        specs = (
            (1, "southwest", 0, True, "moving clockwise through the west side"),
            (2, "north", 2, False, "moving counter-clockwise from the north side"),
            (3, "southeast", 4, True, "moving clockwise through the east side"),
        )
        targets: list[_TargetOption] = []
        for flag, sector, start, clockwise, state in specs:
            route = self._patrol_route(
                circuit,
                start=start,
                clockwise=clockwise,
            )
            launchers = self._scud_group(
                m,
                iran,
                f"{sector.title()} urban Scud launchers",
                route[0],
                heading=int(route[0].heading_between_point(route[1])),
                moving=True,
                route=route,
            )
            targets.append(_TargetOption(flag, sector, search_center, launchers, state))
        return tuple(targets)

    def _spawn_city_traffic(
        self, m: Mission, iran: Country, circuit: Sequence[Point]
    ) -> tuple[VehicleGroup, VehicleGroup]:
        """Put two unarmed traffic streams on the circuit for visual clutter."""
        routes = (
            self._patrol_route(circuit, start=1, clockwise=True),
            self._patrol_route(circuit, start=3, clockwise=False),
        )
        groups: list[VehicleGroup] = []
        for index, route in enumerate(routes, start=1):
            traffic = m.vehicle_group_platoon(
                iran,
                f"Bandar Abbas local traffic {index}",
                list(_TRAFFIC_TYPES),
                position=route[0],
                heading=int(route[0].heading_between_point(route[1])),
                formation=VehicleGroup.Formation.Line,
                move_formation=PointAction.OnRoad,
            )
            set_skill(traffic, Skill.Average)
            for waypoint in route[1:]:
                traffic.add_waypoint(
                    waypoint,
                    move_formation=PointAction.OnRoad,
                    speed=_TRAFFIC_SPEED_KPH,
                )
            groups.append(traffic)
        return groups[0], groups[1]

    @staticmethod
    def _spawn_player(
        m: Mission, usa: Country, khasab: Airport, search_center: Point
    ) -> FlyingGroup:
        """Give both Hornets four IR Mavericks for repeated moving shots."""
        razor = m.flight_group_from_airport(
            country=usa,
            name="Razor",
            aircraft_type=planes.FA_18C_hornet,
            airport=khasab,
            maintask=task.CAS,
            start_type=StartType.Warm,
            group_size=2,
        )
        razor.units[0].skill = Skill.Player
        razor.units[1].skill = Skill.High
        for unit in razor.units:
            loadout.arm_unit(unit, planes.FA_18C_hornet, _HORNET_FIT.stores)
        loadout.record(m, "Razor", _HORNET_FITS)

        razor.add_runway_waypoint(khasab)
        push = offset(search_center, east_m=-9_000, north_m=-12_000)
        razor.add_waypoint(
            push,
            altitude=_CRUISE_ALTITUDE_M,
            speed=_CRUISE_SPEED_KPH,
            name="PUSH",
        )
        razor.add_waypoint(
            search_center,
            altitude=_CRUISE_ALTITUDE_M,
            speed=_CRUISE_SPEED_KPH,
            name="BANDAR ABBAS",
        )
        razor.add_runway_waypoint(khasab)
        razor.land_at(khasab)
        return razor

    def _mission_start_message(self) -> str:
        """State the urban moving-target problem and the positive-ID rule."""
        return (
            "Khasab Control: Razor, the latest pre-launch Reaper sweep shows two "
            "probable Scud launchers circulating through central Bandar Abbas. "
            "They are moving with buses, cars, and cargo traffic. Positive ID, "
            "Scud TELs only. Both jets carry four infrared Mavericks. Destroy "
            "both launchers inside forty minutes. A two-ship MiG-23 response may "
            "commit once you enter the city search area. Recover at Khasab."
        )

    @staticmethod
    def _site_cue(sector: str, state: str) -> str:
        return (
            f"Khasab Control: the latest Reaper moving-target track began in the "
            f"{sector} district. Two probable Scud TELs were {state}. The track "
            "is not current; search the city circuit and confirm the Scud silhouette."
        )

    @staticmethod
    def _draw_plan(plan: PlanOverlay, base: Point, search_center: Point) -> None:
        """Draw ingress and a city-wide search area without freezing the TELs."""
        push = offset(search_center, east_m=-9_000, north_m=-12_000)
        plan.route((base, push, search_center, base), label="URBAN SCUD HUNT")
        plan.objective(search_center, "BANDAR ABBAS SEARCH AREA", radius=5_000)

    def _in_game_briefing(self) -> str:
        return f"""URBAN SCUD HUNT — MOVING-TARGET STRIKE

SITUATION
  A Reaper moving-target sweep shortly before launch picked up two probable
  Iranian Scud-B TELs circulating through central Bandar Abbas. They are using
  buildings and ordinary road traffic as cover. The reported starting district
  and direction are already aging; expect both launchers to keep moving.

MISSION
  Find, positively identify, and destroy both Scud-B launchers before their
  {_LAUNCH_WINDOW_MIN}-minute launch window closes. Weapons are cleared only
  against the TELs. Avoid buses, cars, cargo trucks, and urban structures.

FLIGHT / LOADOUT
  One human F/A-18C lead and one High-skill AI wingman. Hot start and recovery
  at Khasab.
{self.loadout_brief("Razor", _HORNET_FITS)}
  Each Hornet carries four AGM-65F infrared Mavericks, two AIM-120Cs, two
  AIM-9Ms, and one 330-gallon centerline tank. Use the Maverick seeker to
  confirm the long eight-wheel Scud TEL before release.

THREAT / ROE
  A two-ship MiG-23 patrol may commit over the search area. Each aircraft
  carries radar-guided and infrared missiles. No surface-to-air missile belt is
  deployed for this training sortie. Scud TELs only; positive ID is mandatory.

NAVIGATION / COMMS
  Fly Khasab — PUSH — BANDAR ABBAS — Khasab. The F10 plan marks the broad search
  area, not a live TEL position. Razor intra-flight is 251.000 AM; Khasab ATC
  and airfield data are on the kneeboard.

SUCCESS / FAILURE
  Destroy both TELs to close the launch window, then recover at Khasab. If the
  launchers remain operational when the window closes, the strike has failed.
"""

    def readme(self) -> str:
        return f"""# {self.title}

## Mission

A single-player, daylight F/A-18C moving-target exercise from **Khasab**. Two
Scud-B TELs remain on the road inside central **Bandar Abbas** for the entire
{_LAUNCH_WINDOW_MIN}-minute launch window. Their starting district and direction
change between mission runs, and the pre-launch moving-target report is stale by
the time Razor reaches the city.

The TELs drive two laps of an urban circuit among two streams of unarmed buses,
cars, and cargo trucks. Those vehicles are visual clutter, not objectives.
Positive identification and precision employment are the point of the sortie:
weapons are cleared only against the two long eight-wheel Scud launchers.

## Package

Razor is one human F/A-18C lead with one High-skill AI wingman, hot at Khasab.
The broad city search area is drawn on the F10 map, but no mark tracks a mobile
launcher. A two-ship MiG-23 patrol may commit after Razor enters the search area;
each fighter carries radar-guided and infrared missiles. No ground-based SAMs
are deployed in this training version.

## Razor loadout

{self.loadout_table("Razor", _HORNET_FITS)}

Each Hornet has four AGM-65F infrared Mavericks. The flight therefore has four
spare shots after the two required TEL kills, allowing repeated moving-target
practice without restarting after one miss. Two AIM-120Cs, two AIM-9Ms, and a
330-gallon centerline tank complete each fit.

## Navigation, communications, and ROE

Fly **Khasab — PUSH — BANDAR ABBAS — Khasab**. Razor intra-flight is **251.000
AM**; Khasab ATC, airfield, route, and weather data are on the generated
kneeboard. The search-area mark is an area of interest, not a target coordinate.

Weapons are cleared only against positively identified Scud-B TELs. Do not
attack the buses, cars, cargo trucks, or surrounding buildings. Destroy both
TELs before the launch window closes, then recover at Khasab. Leaving either
launcher operational through the window is mission failure.

## Re-generate

```bash
uv run dcs-mission-creator generate {self.name} --output-dir out/{self.name}
```
"""


def main() -> None:
    run_cli(UrbanScudHunt)


if __name__ == "__main__":
    main()
