"""Persian Gulf ``Scud Hunt`` — a daylight, runtime-random Hornet search.

Razor launches from Khasab with one AI wingman. Iranian Scud-B launchers are
randomly either parked near Tal Siah, parked near Baghoo, or moving east on the
road between them. A forty-minute launch window makes finding the right place
matter. Entering the selected search area releases an airborne MiG-23 pair
carrying heat-seeking missiles; there is no cold-ramp scramble sequence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from dcs import action, condition, planes, task, triggers, vehicles
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
from dcs_mission_creator.core.mission_builder import Assembled, MissionBuilder
from dcs_mission_creator.core.mission_kit import offset, set_skill
from dcs_mission_creator.core.placement import convoy_spawn, load_scene
from dcs_mission_creator.core.tasking import apply_ai_difficulty
from dcs_mission_creator.core.triggers import message_to_all, message_to_coalition
from dcs_mission_creator.core.weather import Weather, Wind
from dcs_mission_creator.map_overlay.scene import TacticalScene


@dataclass(frozen=True)
class _TargetOption:
    flag: int
    sector: str
    center: Point
    launchers: VehicleGroup
    state: str


_SITE_FLAG = 910
_LAUNCH_WINDOW_S = 40 * 60
_WARNING_S = _LAUNCH_WINDOW_S - 10 * 60
_CRUISE_ALTITUDE_M = 7_000
_CRUISE_SPEED_KPH = 760
_GROUND_SPEED_KPH = 25
_MIG_ALTITUDE_M = 5_500
_MIG_SPEED_KPH = 780

# These road anchors were snapped against the Persian Gulf overlay's roads
# layer. The route follows the north-of-Bandar-Abbas road corridor from the
# Tal Siah staging area toward Baghoo; every ground waypoint is re-snapped at
# build time and is marked OnRoad in the mission.
_ROAD_ANCHORS = (
    (27.154851, 56.206748),
    (27.192891, 56.268962),
    (27.228667, 56.341183),
    (27.264669, 56.423546),
    (27.278221, 56.451037),
)
_HORNET_FIT = Loadout(
    role="SCUD strike",
    carries=(
        "two 2,000 lb Mk-84 bombs, two AGM-65F IR Mavericks, two AIM-120Cs, "
        "two AIM-9Ms, and one 330-gallon centerline tank"
    ),
    stores=(
        (1, "AIM_9M_Sidewinder_IR_AAM"),
        (2, "Mk_84___2000lb_GP_Bomb_LD"),
        (3, "LAU_117_AGM_65F"),
        (4, "AIM_120C_AMRAAM___Active_Radar_AAM"),
        (5, "FPU_8A_Fuel_Tank_330_gallons"),
        (6, "AIM_120C_AMRAAM___Active_Radar_AAM"),
        (7, "LAU_117_AGM_65F"),
        (8, "Mk_84___2000lb_GP_Bomb_LD"),
        (9, "AIM_9M_Sidewinder_IR_AAM"),
    ),
)
_HORNET_FITS = (_HORNET_FIT, _HORNET_FIT)

_MIG_STORES = (
    (2, "R_24R__AA_7_Apex_SA____Semi_Act_Rdr"),
    (3, "APU_60_1M_with_R_60M__AA_8_Aphid_B____IR_AAM_"),
    (5, "APU_60_1M_with_R_60M__AA_8_Aphid_B____IR_AAM_"),
    (6, "R_24T__AA_7_Apex_IR____Infra_Red"),
)


class ScudHunt(MissionBuilder):
    """One human Hornet pilot, a wingman, and a randomized target state."""

    name = "scud_hunt"
    title = "Scud Hunt"
    difficulty = Difficulty.TRAINED
    terrain = PersianGulf
    blue_task = (
        "Find and destroy both Scud-B launchers north of Bandar Abbas before "
        "their 40-minute launch window closes. Their site or movement state "
        "changes at runtime. Expect MiG-23s armed with radar-guided and "
        "heat-seeking missiles."
    )
    red_task = (
        "Move or conceal the Scud launchers in the Bandar Abbas corridor. "
        "Complete launch preparations before the search flight can destroy both."
    )
    start_time = datetime(2026, 10, 18, 10, 0, tzinfo=timezone.utc)
    weather = Weather(
        name="Clear Persian Gulf morning",
        season_temperature=29,
        clouds_base=5_500,
        clouds_thickness=400,
        clouds_density=1,
        visibility_distance=50_000,
        wind_at_ground=Wind(direction=310, speed=3),
        wind_at_2000=Wind(direction=320, speed=7),
        wind_at_8000=Wind(direction=330, speed=12),
    )

    def __init__(self, *, players: int = 2) -> None:
        # One DCS Player slot and one High-skill AI wingman make this a true
        # single-player sortie while preserving the project's mixed-flight fit
        # bookkeeping. Like bagram_wildcard, this mission is intentionally fixed.
        if players != 2:
            raise ValueError("scud_hunt is fixed at one player plus one AI wingman")
        super().__init__(players=2)

    def _assemble(self, m: Mission, plan: PlanOverlay) -> Assembled:
        khasab = self._terrain.airports["Khasab"]
        bandar_abbas = self._terrain.airports["Bandar Abbas Intl"]
        khasab.set_blue()
        bandar_abbas.set_red()

        scene = load_scene("persiangulf")
        usa, iran = m.country("USA"), m.country("Iran")
        west, east, route = self._target_points(scene)
        search_center = west.midpoint(east)

        razor = self._spawn_player(m, usa, khasab, search_center)
        targets = self._spawn_target_options(m, iran, west, east, route)
        migs = self._spawn_intercept(m, iran, search_center)
        self._add_runtime_logic(m, razor, targets, migs)
        self._draw_plan(plan, khasab.position, search_center)
        return Assembled(scene.overlay)

    def _target_points(self, scene: TacticalScene) -> tuple[Point, Point, list[Point]]:
        road = [
            convoy_spawn(scene, self.at(lat, lng), radius_m=1_500)
            for lat, lng in _ROAD_ANCHORS
        ]
        return road[0], road[-1], road

    @staticmethod
    def _spawn_player(
        m: Mission, usa: Country, khasab: Airport, search_center: Point
    ) -> FlyingGroup:
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
            name="SEARCH AREA",
        )
        razor.add_runway_waypoint(khasab)
        razor.land_at(khasab)
        return razor

    def _spawn_target_options(
        self,
        m: Mission,
        iran: Country,
        west: Point,
        east: Point,
        route: Sequence[Point],
    ) -> tuple[_TargetOption, ...]:
        west_parked = self._scud_group(m, iran, "West site launchers", west, heading=90)
        east_parked = self._scud_group(m, iran, "East site launchers", east, heading=90)
        mobile = self._scud_group(
            m,
            iran,
            "Road-mobile launchers",
            route[0],
            heading=int(route[0].heading_between_point(route[1])),
            moving=True,
            route=route,
        )
        # Option order is also the runtime flag value. DCS chooses it after the
        # .miz is loaded, so replaying the same file can select another case.
        return (
            _TargetOption(1, "west", west, west_parked, "parked near Tal Siah"),
            _TargetOption(2, "east", east, east_parked, "parked near Baghoo"),
            _TargetOption(
                3, "road", west.midpoint(east), mobile, "moving east on the road"
            ),
        )

    @staticmethod
    def _scud_group(
        m: Mission,
        iran: Country,
        name: str,
        position: Point,
        *,
        heading: int,
        moving: bool = False,
        route: Sequence[Point] | None = None,
    ) -> VehicleGroup:
        launchers = m.vehicle_group(
            iran,
            name,
            vehicles.MissilesSS.Scud_B,
            position=position,
            heading=heading,
            group_size=2,
            formation=(
                VehicleGroup.Formation.Line
                if moving
                else VehicleGroup.Formation.Scattered
            ),
            move_formation=PointAction.OnRoad if moving else PointAction.OffRoad,
        )
        launchers.late_activation = True
        set_skill(launchers, Skill.Average)
        if moving:
            if route is None:
                raise ValueError("a moving Scud group requires a road route")
            for waypoint in route[1:]:
                launchers.add_waypoint(
                    waypoint,
                    move_formation=PointAction.OnRoad,
                    speed=_GROUND_SPEED_KPH,
                )
        return launchers

    def _spawn_intercept(
        self, m: Mission, iran: Country, search_center: Point
    ) -> FlyingGroup:
        spawn = offset(search_center, east_m=26_000, north_m=32_000)
        migs = m.flight_group_inflight(
            iran,
            "MiG-23 patrol",
            planes.MiG_23MLD,
            position=spawn,
            altitude=_MIG_ALTITUDE_M,
            speed=_MIG_SPEED_KPH,
            maintask=task.CAP,
            group_size=2,
        )
        migs.late_activation = True
        migs.points[0].tasks[0] = task.EngageTargets(90_000, [task.Targets.All.Air])
        migs.add_waypoint(
            search_center,
            altitude=_MIG_ALTITUDE_M,
            speed=_MIG_SPEED_KPH,
            name="INTERCEPT",
        )
        loadout.arm_group(migs, planes.MiG_23MLD, _MIG_STORES)
        set_skill(migs, Skill.High)
        apply_ai_difficulty(migs, self.difficulty)
        return migs

    def _add_runtime_logic(
        self,
        m: Mission,
        razor: FlyingGroup,
        targets: Sequence[_TargetOption],
        migs: FlyingGroup,
    ) -> None:
        chooser = triggers.TriggerStart(comment="Choose runtime Scud location/state")
        chooser.add_action(action.SetFlagRandom(_SITE_FLAG, 1, len(targets)))
        m.triggerrules.triggers.append(chooser)

        for target in targets:
            cue = self._site_cue(target.sector, target.state)
            message_to_coalition(
                m,
                comment=f"Control reports {target.sector} Scud intelligence",
                conditions=(
                    condition.FlagEquals(_SITE_FLAG, target.flag),
                    condition.TimeAfter(seconds=25),
                ),
                voice=self._voice,
                text=cue,
                seconds=20,
            )
            release = triggers.TriggerOnce(
                comment=f"Activate selected {target.sector} Scud group"
            )
            release.add_condition(condition.FlagEquals(_SITE_FLAG, target.flag))
            release.add_action(action.ActivateGroup(target.launchers.id))
            m.triggerrules.triggers.append(release)

            self._add_mig_trigger(
                m,
                razor,
                target=target,
                migs=migs,
            )
            self._add_target_outcome(m, target)

        self._add_clock(m, targets)
        mission_start = (
            "Khasab Control: Razor, launch for a daylight search north of "
            "Bandar Abbas. Two Scud launchers are the frag. Site and movement "
            "state are randomized each run; destroy both within forty minutes. "
            "A two-ship MiG-23 response may commit inside the search area. "
            "Each MiG carries one radar-guided R-24R, one infrared R-24T, "
            "and two infrared R-60s. Recover at Khasab."
        )
        from dcs_mission_creator.core.triggers import intro

        intro(
            m,
            comment="Scud Hunt mission brief",
            voice=self._voice,
            text=mission_start,
        )

    def _add_mig_trigger(
        self,
        m: Mission,
        razor: FlyingGroup,
        *,
        target: _TargetOption,
        migs: FlyingGroup,
    ) -> None:
        zone = m.triggers.add_triggerzone(
            position=target.center,
            radius=24_000,
            hidden=True,
            name=f"{target.sector.title()} Scud search area",
        )
        text = (
            f"Khasab Control: Razor, two MiG-23s are airborne near the "
            f"{target.sector} sector. They carry radar-guided and heat-seeking "
            "missiles; the pair is closing on your position."
        )
        response = triggers.TriggerOnce(
            comment=f"Release {target.sector} airborne MiG-23 pair"
        )
        response.add_condition(condition.FlagEquals(_SITE_FLAG, target.flag))
        response.add_condition(condition.GroupAlive(target.launchers.id))
        response.add_condition(condition.PartOfGroupInZone(razor.id, zone.id))
        response.add_action(action.ActivateGroup(migs.id))
        response.add_action(
            action.MessageToCoalition(action.Coalition.Blue, m.string(text), seconds=20)
        )
        self._voice.attach_to_coalition(
            m,
            response,
            text,
            coalition="blue",
        )
        m.triggerrules.triggers.append(response)

    def _add_target_outcome(self, m: Mission, target: _TargetOption) -> None:
        text = (
            "Khasab Control: Razor, both Scud launchers are destroyed. Launch window "
            "closed. Recover at Khasab."
        )
        message_to_all(
            m,
            comment="Scud launchers destroyed",
            conditions=(
                condition.FlagEquals(_SITE_FLAG, target.flag),
                condition.GroupDead(target.launchers.id),
            ),
            voice=self._voice,
            text=text,
            seconds=25,
        )

    def _add_clock(self, m: Mission, targets: Sequence[_TargetOption]) -> None:
        for target in targets:
            message_to_coalition(
                m,
                comment=f"Ten minutes remain for {target.sector} site",
                conditions=(
                    condition.FlagEquals(_SITE_FLAG, target.flag),
                    condition.GroupAlive(target.launchers.id),
                    condition.TimeAfter(seconds=_WARNING_S),
                ),
                voice=self._voice,
                text=(
                    "Khasab Control: Ten minutes until the reported Scud launch window "
                    "closes. Locate the launchers now."
                ),
                seconds=18,
            )
            message_to_all(
                m,
                comment=f"Scud launch window missed at {target.sector} site",
                conditions=(
                    condition.FlagEquals(_SITE_FLAG, target.flag),
                    condition.GroupAlive(target.launchers.id),
                    condition.TimeAfter(seconds=_LAUNCH_WINDOW_S),
                ),
                voice=self._voice,
                text=(
                    "Khasab Control: The Scud launch window has closed. The launchers "
                    "remain operational; mission failed. Recover at Khasab."
                ),
                seconds=25,
            )

    @staticmethod
    def _site_cue(sector: str, state: str) -> str:
        if state == "moving east on the road":
            return (
                "Khasab Control: SIGINT reports two Scud launchers moving east from the "
                "Tal Siah storage area toward Baghoo. Search the road corridor."
            )
        if sector == "west":
            return (
                "Khasab Control: SIGINT places the launchers at a storage site near Tal "
                "Siah. No exact position; search the western side of the area."
            )
        return (
            "Khasab Control: SIGINT places the launchers at a launch site near Baghoo. "
            "No exact position; search the eastern side of the area."
        )

    @staticmethod
    def _draw_plan(plan: PlanOverlay, base: Point, search_center: Point) -> None:
        push = offset(search_center, east_m=-9_000, north_m=-12_000)
        plan.route((base, push, search_center, base), label="SCUD HUNT")
        plan.objective(search_center, "SIGINT SEARCH AREA", radius=22_000)

    def _in_game_briefing(self) -> str:
        return f"""SCUD HUNT — DAYLIGHT STRIKE

SITUATION
  Iranian forces are preparing two Scud-B launchers north of Bandar Abbas.
  Runtime intelligence selects one of three cases: parked near Tal Siah,
  parked near Baghoo, or moving east along the road between those areas. The
  exact site changes on every mission run. Destroy both launchers before the
  forty-minute launch window closes.

FLIGHT
  One human F/A-18C lead and one High-skill AI wingman. Hot start at Khasab;
  recover at Khasab. Daylight, clear visibility. Khasab Control reports which sector
  intelligence has selected but does not mark the launchers on the map.

LOADOUT
{self.loadout_brief("Razor", _HORNET_FITS)}
  Both Hornets carry two 2,000 lb Mk-84s, two AGM-65F IR Mavericks, two AIM-120Cs,
  two AIM-9Ms, and one 330-gallon centerline tank. Use Mavericks against
  launchers on the move; Mk-84s are available for parked launchers.

THREAT / ROE
  A two-ship MiG-23 patrol activates when Razor enters the selected search
  area. Each carries one R-24R semi-active radar missile, one R-24T infrared
  missile, and two R-60M infrared missiles. Defend against both radar-guided
  and heat-seeking shots. No surface-to-air missile belt is deployed in this
  training version.

TIMING
  The launch window closes 40 minutes after mission start; Control calls the
  ten-minute warning. Destroy both TELs to close the threat, then recover.
"""

    def readme(self) -> str:
        return f"""# {self.title}

## Mission

A single-player, daylight F/A-18C strike from **Khasab** into a compact road
corridor north of **Bandar Abbas**. One human lead flies with a High-skill AI
wingman. Two Scud-B launchers are the objective; Khasab Control names the selected
sector, but does not put the target on the map.

At runtime DCS chooses one of three target states: launchers parked near Tal
Siah, parked near Baghoo, or moving east between the two on the road. The same
`.miz` can therefore give you a different search on replay. You have **40
minutes** from mission start before the launch window closes; Control calls when
ten minutes remain.

## Razor loadout

Both Hornets carry the same fit:

{self.loadout_table("Razor", _HORNET_FITS)}

This provides two 2,000 lb Mk-84s for parked targets, two AGM-65F infrared
Mavericks for standoff shots against moving TELs, two AIM-120Cs, two AIM-9Ms,
and a 330-gallon centerline tank. The stores were checked against the installed
F/A-18C module and ED's shipped payload stations.

## Opposition

Entering the active search area releases a late-activated, already-airborne
two-ship of MiG-23MLDs. Each carries one R-24R semi-active radar missile, one
R-24T infrared missile, and two R-60M heat-seeking missiles. No ground-based
SAMs are deployed. Destroy the Scuds, defend if the MiGs commit, and recover at
Khasab.

## Re-generate

```bash
uv run dcs-mission-creator generate {self.name} --output-dir out/{self.name}
```
"""


def main() -> None:
    run_cli(ScudHunt)


if __name__ == "__main__":
    main()
