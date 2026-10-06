"""Afghanistan ``Bagram Wildcard`` — a replayable eight-aircraft fighter sweep.

Razor is one player F/A-18C and one AI wingman, hot at Bagram with identical
ten-AMRAAM fits.  Magic is already airborne west of the field.  Crossing the
push line makes DCS choose one of eight complete adversary packages at runtime,
so replaying the *same* ``.miz`` changes the aircraft, group sizes, approach
axes, missile fits and pilot quality rather than merely changing a Python build.

Each package contains exactly eight aircraft in five one-to-three-ship waves.
The next wave is released only after the current one has been destroyed, plus
a short reset interval; the sortie is therefore a spaced fighter gauntlet, not
one eight-aircraft furball.  The extremes are an all-MiG-23 package and an
all-Su-33 package, with six mixed packages between them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from dcs import action, condition, planes, task, triggers
from dcs.country import Country
from dcs.mapping import Point
from dcs.mission import Mission, StartType
from dcs.terrain.afghanistan.afghanistan import Afghanistan
from dcs.terrain.terrain import Airport
from dcs.unit import Skill
from dcs.unitgroup import FlyingGroup

from dcs_mission_creator.core import (
    loadout,
    sanctuary as sanc,
    triggers as mission_triggers,
)
from dcs_mission_creator.core.cli import run_cli
from dcs_mission_creator.core.difficulty import Difficulty
from dcs_mission_creator.core.loadout import Loadout
from dcs_mission_creator.core.map_draw import PlanOverlay
from dcs_mission_creator.core.mission_builder import Assembled, MissionBuilder
from dcs_mission_creator.core.mission_kit import arm, offset, set_skill
from dcs_mission_creator.core.placement import load_scene
from dcs_mission_creator.core.tasking import apply_ai_difficulty
from dcs_mission_creator.core.weather import Weather, Wind
from dcs_mission_creator.map_overlay.scene import TacticalScene

_MAGIC_FREQUENCY_MHZ = 251
_CRUISE_ALTITUDE_M = 7_600
_CRUISE_SPEED_KPH = 760
_BANDIT_SPEED_KPH = 780
_WAVE_RESET_S = 75

# Mission flags are deliberately well above the low values used by pydcs and
# the project's support helpers.  DCS selects this at mission start, not while
# Python builds the file, which is what makes one saved .miz replay differently.
_PACKAGE_FLAG = 910
_RELEASED_FLAG_BASE = 930
_CLEARED_FLAG_BASE = 1_000

_PUSH = (35.0200, 69.3800)
_CAP = (35.1200, 69.6000)
_EGRESS = (35.0100, 69.3900)

# Surveyed approach axes around the north-eastern Bagram working area.  All
# airborne starts are high enough to clear the Hindu Kush beneath them.
_SPAWNS = (
    ("north", 35.5700, 69.5500),
    ("north-east", 35.4500, 70.0000),
    ("east", 35.1800, 70.1800),
    ("south-east", 34.8300, 70.0000),
    ("north-west", 35.4300, 69.1600),
)

# Ten AMRAAMs are possible because DCS's Hornet accepts the dual LAU-115/127
# rack on stations 2, 3, 7 and 8.  ED's stock presets only demonstrate that
# rack on 2 and 8, so the loadout audit calls the inner pair unusual even
# though the module and Mission Editor support the familiar 10x AMRAAM fit.
_HORNET_FIT = Loadout(
    role="AIM-120C*10",
    carries="ten AIM-120C, two AIM-9X and one 330 gal centerline tank",
    stores=(
        (1, "AIM_9X_Sidewinder_IR_AAM"),
        (2, "LAU_115_2_LAU_127_AIM_120C"),
        (3, "LAU_115_2_LAU_127_AIM_120C"),
        (4, "AIM_120C_AMRAAM___Active_Radar_AAM"),
        (5, "FPU_8A_Fuel_Tank_330_gallons"),
        (6, "AIM_120C_AMRAAM___Active_Radar_AAM"),
        (7, "LAU_115_2_LAU_127_AIM_120C"),
        (8, "LAU_115_2_LAU_127_AIM_120C"),
        (9, "AIM_9X_Sidewinder_IR_AAM"),
    ),
)
_HORNET_FITS = (_HORNET_FIT, _HORNET_FIT)


@dataclass(frozen=True)
class _EnemyFit:
    name: str
    stores: tuple[tuple[int, str], ...]


_MIG23_RADAR = _EnemyFit(
    "R-24R / R-60M",
    (
        (2, "R_24R__AA_7_Apex_SA____Semi_Act_Rdr"),
        (3, "APU_60_2M_with_2_x_R_60M__AA_8_Aphid_B____IR_AAM__"),
        (4, "Fuel_tank_800L"),
        (5, "APU_60_2M_with_2_x_R_60M__AA_8_Aphid_B____IR_AAM___"),
        (6, "R_24R__AA_7_Apex_SA____Semi_Act_Rdr"),
    ),
)
_MIG23_MIXED = _EnemyFit(
    "R-24R/T / R-60M",
    (
        (2, "R_24T__AA_7_Apex_IR____Infra_Red"),
        (3, "APU_60_2M_with_2_x_R_60M__AA_8_Aphid_B____IR_AAM__"),
        (4, "Fuel_tank_800L"),
        (5, "APU_60_2M_with_2_x_R_60M__AA_8_Aphid_B____IR_AAM___"),
        (6, "R_24R__AA_7_Apex_SA____Semi_Act_Rdr"),
    ),
)
_MIG29A_SEMI = _EnemyFit(
    "R-27R / R-73",
    (
        (1, "R_73__AA_11_Archer____Infra_Red"),
        (2, "R_73__AA_11_Archer____Infra_Red"),
        (3, "R_27R__AA_10_Alamo_A____Semi_Act_Rdr"),
        (4, "Fuel_tank_1400L"),
        (5, "R_27R__AA_10_Alamo_A____Semi_Act_Rdr"),
        (6, "R_73__AA_11_Archer____Infra_Red"),
        (7, "R_73__AA_11_Archer____Infra_Red"),
    ),
)
_MIG29S_ACTIVE = _EnemyFit(
    "R-77 / R-73",
    (
        (1, "R_73__AA_11_Archer____Infra_Red"),
        (2, "R_77__AA_12_Adder____Active_Rdr"),
        (3, "R_77__AA_12_Adder____Active_Rdr"),
        (4, "Fuel_tank_1400L"),
        (5, "R_77__AA_12_Adder____Active_Rdr"),
        (6, "R_77__AA_12_Adder____Active_Rdr"),
        (7, "R_73__AA_11_Archer____Infra_Red"),
    ),
)
_SU27_IR = _EnemyFit(
    "R-27ET/ER / R-73",
    (
        (1, "R_73__AA_11_Archer____Infra_Red"),
        (2, "R_73__AA_11_Archer____Infra_Red"),
        (3, "R_27ET__AA_10_Alamo_D____IR_Extended_Range"),
        (4, "R_27ER__AA_10_Alamo_C____Semi_Act_Extended_Range"),
        (5, "R_27ER__AA_10_Alamo_C____Semi_Act_Extended_Range"),
        (6, "R_27ER__AA_10_Alamo_C____Semi_Act_Extended_Range"),
        (7, "R_27ER__AA_10_Alamo_C____Semi_Act_Extended_Range"),
        (8, "R_27ET__AA_10_Alamo_D____IR_Extended_Range"),
        (9, "R_73__AA_11_Archer____Infra_Red"),
        (10, "R_73__AA_11_Archer____Infra_Red"),
    ),
)
_SU33_SEMI = _EnemyFit(
    "R-27R/ER / R-73",
    (
        (1, "R_73__AA_11_Archer____Infra_Red"),
        (2, "R_73__AA_11_Archer____Infra_Red"),
        (3, "R_27R__AA_10_Alamo_A____Semi_Act_Rdr"),
        (4, "R_27ER__AA_10_Alamo_C____Semi_Act_Extended_Range"),
        (5, "R_27ER__AA_10_Alamo_C____Semi_Act_Extended_Range"),
        (6, "R_27ER__AA_10_Alamo_C____Semi_Act_Extended_Range"),
        (7, "R_27ER__AA_10_Alamo_C____Semi_Act_Extended_Range"),
        (8, "R_27ER__AA_10_Alamo_C____Semi_Act_Extended_Range"),
        (9, "R_27ER__AA_10_Alamo_C____Semi_Act_Extended_Range"),
        (10, "R_27R__AA_10_Alamo_A____Semi_Act_Rdr"),
        (11, "R_73__AA_11_Archer____Infra_Red"),
        (12, "R_73__AA_11_Archer____Infra_Red"),
    ),
)
_SU33_IR = _EnemyFit(
    "R-27ET/ER / R-73",
    (
        (2, "R_73__AA_11_Archer____Infra_Red"),
        (3, "R_27ET__AA_10_Alamo_D____IR_Extended_Range"),
        (4, "R_27ER__AA_10_Alamo_C____Semi_Act_Extended_Range"),
        (5, "R_27ER__AA_10_Alamo_C____Semi_Act_Extended_Range"),
        (6, "R_27ER__AA_10_Alamo_C____Semi_Act_Extended_Range"),
        (7, "R_27ER__AA_10_Alamo_C____Semi_Act_Extended_Range"),
        (8, "R_27ER__AA_10_Alamo_C____Semi_Act_Extended_Range"),
        (9, "R_27ER__AA_10_Alamo_C____Semi_Act_Extended_Range"),
        (10, "R_27ET__AA_10_Alamo_D____IR_Extended_Range"),
        (11, "R_73__AA_11_Archer____Infra_Red"),
    ),
)
_SU34_ACTIVE = _EnemyFit(
    "R-77 / R-73",
    (
        (2, "R_73__AA_11_Archer____Infra_Red"),
        (3, "R_77__AA_12_Adder____Active_Rdr"),
        (10, "R_77__AA_12_Adder____Active_Rdr"),
        (11, "R_73__AA_11_Archer____Infra_Red"),
    ),
)


@dataclass(frozen=True)
class _Bandit:
    aircraft: type[planes.PlaneType]
    size: int
    fit: _EnemyFit
    skill: Skill
    behavior: Difficulty
    spawn: int
    altitude_m: int


def _b(
    aircraft: type[planes.PlaneType],
    size: int,
    fit: _EnemyFit,
    skill: Skill,
    behavior: Difficulty,
    spawn: int,
    altitude_m: int,
) -> _Bandit:
    return _Bandit(aircraft, size, fit, skill, behavior, spawn, altitude_m)


# Every row sums to exactly eight aircraft.  The first two are intentional edge
# cases; the remaining rows mix generations, seekers, pilot skill and geometry.
_PACKAGES = (
    (
        _b(
            planes.MiG_23MLD,
            1,
            _MIG23_RADAR,
            Skill.Average,
            Difficulty.RECRUIT,
            0,
            6_500,
        ),
        _b(
            planes.MiG_23MLD,
            2,
            _MIG23_MIXED,
            Skill.Random,
            Difficulty.RECRUIT,
            2,
            7_200,
        ),
        _b(planes.MiG_23MLD, 3, _MIG23_RADAR, Skill.Good, Difficulty.TRAINED, 1, 7_800),
        _b(
            planes.MiG_23MLD,
            1,
            _MIG23_MIXED,
            Skill.Average,
            Difficulty.RECRUIT,
            3,
            6_800,
        ),
        _b(planes.MiG_23MLD, 1, _MIG23_RADAR, Skill.Good, Difficulty.TRAINED, 4, 8_200),
    ),
    (
        _b(planes.Su_33, 2, _SU33_SEMI, Skill.High, Difficulty.VETERAN, 1, 9_000),
        _b(planes.Su_33, 1, _SU33_IR, Skill.Excellent, Difficulty.ACE, 3, 8_200),
        _b(planes.Su_33, 2, _SU33_SEMI, Skill.Excellent, Difficulty.ACE, 0, 9_500),
        _b(planes.Su_33, 1, _SU33_IR, Skill.High, Difficulty.VETERAN, 2, 8_800),
        _b(planes.Su_33, 2, _SU33_SEMI, Skill.Excellent, Difficulty.ACE, 4, 9_200),
    ),
    (
        _b(planes.MiG_29A, 2, _MIG29A_SEMI, Skill.Good, Difficulty.TRAINED, 2, 8_000),
        _b(planes.Su_34, 1, _SU34_ACTIVE, Skill.Random, Difficulty.VETERAN, 0, 9_200),
        _b(planes.MiG_29S, 2, _MIG29S_ACTIVE, Skill.High, Difficulty.VETERAN, 3, 8_600),
        _b(
            planes.MiG_23MLD,
            1,
            _MIG23_MIXED,
            Skill.Average,
            Difficulty.RECRUIT,
            4,
            6_700,
        ),
        _b(planes.Su_33, 2, _SU33_IR, Skill.High, Difficulty.VETERAN, 1, 9_000),
    ),
    (
        _b(planes.Su_34, 1, _SU34_ACTIVE, Skill.Good, Difficulty.TRAINED, 3, 8_500),
        _b(
            planes.MiG_23MLD,
            2,
            _MIG23_RADAR,
            Skill.Random,
            Difficulty.RECRUIT,
            0,
            7_000,
        ),
        _b(planes.Su_27, 2, _SU27_IR, Skill.High, Difficulty.VETERAN, 4, 9_000),
        _b(planes.MiG_29S, 2, _MIG29S_ACTIVE, Skill.Good, Difficulty.TRAINED, 2, 8_200),
        _b(planes.MiG_29A, 1, _MIG29A_SEMI, Skill.Excellent, Difficulty.ACE, 1, 9_300),
    ),
    (
        _b(planes.MiG_29S, 2, _MIG29S_ACTIVE, Skill.High, Difficulty.VETERAN, 1, 8_800),
        _b(
            planes.MiG_23MLD,
            1,
            _MIG23_MIXED,
            Skill.Average,
            Difficulty.RECRUIT,
            3,
            6_600,
        ),
        _b(planes.Su_33, 2, _SU33_SEMI, Skill.Random, Difficulty.VETERAN, 4, 9_400),
        _b(planes.Su_34, 2, _SU34_ACTIVE, Skill.Good, Difficulty.TRAINED, 0, 8_300),
        _b(planes.MiG_29A, 1, _MIG29A_SEMI, Skill.High, Difficulty.VETERAN, 2, 8_700),
    ),
    (
        _b(planes.Su_27, 2, _SU27_IR, Skill.Good, Difficulty.TRAINED, 4, 8_500),
        _b(
            planes.MiG_29S, 2, _MIG29S_ACTIVE, Skill.Excellent, Difficulty.ACE, 2, 9_300
        ),
        _b(planes.Su_34, 1, _SU34_ACTIVE, Skill.Random, Difficulty.TRAINED, 0, 8_000),
        _b(
            planes.MiG_23MLD,
            2,
            _MIG23_RADAR,
            Skill.Average,
            Difficulty.RECRUIT,
            3,
            6_900,
        ),
        _b(planes.Su_33, 1, _SU33_IR, Skill.High, Difficulty.VETERAN, 1, 9_000),
    ),
    (
        _b(planes.MiG_23MLD, 1, _MIG23_MIXED, Skill.Good, Difficulty.TRAINED, 0, 7_000),
        _b(planes.Su_34, 1, _SU34_ACTIVE, Skill.High, Difficulty.VETERAN, 3, 9_000),
        _b(planes.MiG_29A, 2, _MIG29A_SEMI, Skill.Random, Difficulty.TRAINED, 1, 8_100),
        _b(planes.Su_33, 2, _SU33_SEMI, Skill.Excellent, Difficulty.ACE, 4, 9_500),
        _b(planes.MiG_29S, 2, _MIG29S_ACTIVE, Skill.High, Difficulty.VETERAN, 2, 8_700),
    ),
    (
        _b(planes.Su_33, 2, _SU33_IR, Skill.High, Difficulty.VETERAN, 2, 9_000),
        _b(planes.MiG_29S, 3, _MIG29S_ACTIVE, Skill.Good, Difficulty.TRAINED, 0, 8_300),
        _b(planes.Su_34, 1, _SU34_ACTIVE, Skill.Excellent, Difficulty.ACE, 3, 9_400),
        _b(
            planes.MiG_23MLD,
            1,
            _MIG23_RADAR,
            Skill.Random,
            Difficulty.RECRUIT,
            1,
            6_800,
        ),
        _b(planes.Su_27, 1, _SU27_IR, Skill.Excellent, Difficulty.ACE, 4, 9_600),
    ),
)


@dataclass(frozen=True)
class _Scene:
    bagram: Airport
    kabul: Airport
    push: Point
    cap: Point
    egress: Point
    spawns: tuple[Point, ...]
    overlay: TacticalScene


class BagramWildcard(MissionBuilder):
    """One human Hornet lead, one AI wingman and runtime-random opposition."""

    name = "bagram_wildcard"
    title = "Bagram Wildcard"
    difficulty = Difficulty.TRAINED
    terrain = Afghanistan
    blue_task = (
        "Take Razor to the north-eastern Bagram CAP box and clear eight hostile "
        "aircraft under Magic control; composition and axes are unknown."
    )
    red_task = (
        "Commit one dispersed eight-aircraft composite package in successive waves, "
        "deny the Bagram fighter corridor, then withdraw surviving aircraft south."
    )
    start_time = datetime(2026, 10, 23, 10, 20, tzinfo=timezone.utc)
    weather = Weather(
        name="Clear central Afghanistan late morning",
        season_temperature=19,
        clouds_base=6_000,
        clouds_thickness=300,
        clouds_density=1,
        visibility_distance=55_000,
        wind_at_ground=Wind(direction=300, speed=3),
        wind_at_2000=Wind(direction=310, speed=7),
        wind_at_8000=Wind(direction=320, speed=15),
    )

    def __init__(self, *, players: int = 2) -> None:
        if players != 2:
            raise ValueError(
                "bagram_wildcard is fixed at one player plus one AI wingman"
            )
        super().__init__(players=2)

    def _assemble(self, m: Mission, plan: PlanOverlay) -> Assembled:
        scene = self._scene()
        scene.bagram.set_blue()
        scene.kabul.set_red()
        usa, russia = m.country("USA"), m.country("Russia")

        razor = self._spawn_razor(m, usa, scene)
        magic, magic_track = self._spawn_magic(m, usa, scene)
        packages = self._spawn_packages(m, russia, scene)
        home, enemy = self._spawn_sanctuaries(m, usa, russia, scene)
        self._add_runtime_logic(m, razor, packages)
        briefed = self._draw_plan(plan, scene, magic_track, home, enemy)
        return Assembled(scene.overlay.overlay, briefed)

    def _scene(self) -> _Scene:
        return _Scene(
            bagram=self._terrain.airports["Bagram"],
            kabul=self._terrain.airports["Kabul"],
            push=self.at(*_PUSH),
            cap=self.at(*_CAP),
            egress=self.at(*_EGRESS),
            spawns=tuple(self.at(lat, lon) for _, lat, lon in _SPAWNS),
            overlay=load_scene("afghanistan"),
        )

    @staticmethod
    def _spawn_razor(m: Mission, usa: Country, scene: _Scene) -> FlyingGroup:
        razor = m.flight_group_from_airport(
            usa,
            "Razor",
            planes.FA_18C_hornet,
            scene.bagram,
            maintask=task.CAP,
            start_type=StartType.Warm,
            group_size=2,
        )
        razor.units[0].skill = Skill.Player
        razor.units[1].skill = Skill.Excellent
        for unit in razor.units:
            loadout.arm_unit(unit, planes.FA_18C_hornet, _HORNET_FIT.stores)
        loadout.record(m, "Razor", _HORNET_FITS)

        razor.add_runway_waypoint(scene.bagram)
        razor.add_waypoint(
            scene.push,
            altitude=_CRUISE_ALTITUDE_M,
            speed=_CRUISE_SPEED_KPH,
            name="PUSH",
        )
        station = razor.add_waypoint(
            scene.cap,
            altitude=_CRUISE_ALTITUDE_M,
            speed=_CRUISE_SPEED_KPH,
            name="CAP",
        )
        station.tasks.append(
            task.OrbitAction(
                _CRUISE_ALTITUDE_M,
                _CRUISE_SPEED_KPH,
                task.OrbitAction.OrbitPattern.RaceTrack,
            )
        )
        razor.add_waypoint(
            scene.egress,
            altitude=_CRUISE_ALTITUDE_M,
            speed=_CRUISE_SPEED_KPH,
            name="EGRESS",
        )
        razor.add_runway_waypoint(scene.bagram)
        razor.land_at(scene.bagram)
        return razor

    @staticmethod
    def _spawn_magic(
        m: Mission, usa: Country, scene: _Scene
    ) -> tuple[FlyingGroup, tuple[Point, Point]]:
        first = offset(scene.bagram.position, east_m=-38_000, north_m=-18_000)
        second = first.point_from_heading(0, 75_000)
        magic = m.awacs_flight(
            usa,
            "Magic",
            planes.E_3A,
            airport=None,
            position=first,
            race_distance=75_000,
            heading=0,
            altitude=9_000,
            speed=740,
            frequency=_MAGIC_FREQUENCY_MHZ,
        )
        return magic, (first, second)

    def _spawn_packages(
        self, m: Mission, russia: Country, scene: _Scene
    ) -> tuple[tuple[FlyingGroup, ...], ...]:
        packages: list[tuple[FlyingGroup, ...]] = []
        for package_number, specs in enumerate(_PACKAGES, start=1):
            groups = tuple(
                self._spawn_bandits(
                    m,
                    russia,
                    scene,
                    package_number=package_number,
                    wave_number=wave_number,
                    spec=spec,
                )
                for wave_number, spec in enumerate(specs, start=1)
            )
            packages.append(groups)
        return tuple(packages)

    @staticmethod
    def _spawn_bandits(
        m: Mission,
        russia: Country,
        scene: _Scene,
        *,
        package_number: int,
        wave_number: int,
        spec: _Bandit,
    ) -> FlyingGroup:
        name = f"Wildcard {package_number}-{wave_number}"
        flight = m.flight_group_inflight(
            russia,
            name,
            spec.aircraft,
            position=scene.spawns[spec.spawn],
            altitude=spec.altitude_m,
            speed=_BANDIT_SPEED_KPH,
            maintask=task.CAP,
            group_size=spec.size,
        )
        flight.late_activation = True
        flight.points[0].tasks[0] = task.EngageTargets(140_000, [task.Targets.All.Air])
        flight.add_waypoint(
            scene.cap,
            altitude=spec.altitude_m,
            speed=_BANDIT_SPEED_KPH,
            name="COMMIT",
        )
        arm(flight, spec.aircraft, spec.fit.stores)
        set_skill(flight, spec.skill)
        apply_ai_difficulty(flight, spec.behavior)
        return flight

    def _spawn_sanctuaries(
        self,
        m: Mission,
        usa: Country,
        russia: Country,
        scene: _Scene,
    ) -> tuple[sanc.Sanctuary, sanc.Sanctuary]:
        home = sanc.build_sanctuary(
            m,
            usa,
            scene.bagram,
            callsign="Bagram shield",
            facing=scene.cap,
            battery=sanc.NASAMS,
            keep_clear=(scene.cap,),
            point_defence=2,
            overlay=scene.overlay.overlay,
            terrain=self._terrain,
        )
        enemy = sanc.build_sanctuary(
            m,
            russia,
            scene.kabul,
            callsign="Kabul shield",
            facing=scene.cap,
            battery=sanc.SA_3,
            enemy=True,
            label="SA-3 Kabul",
            keep_clear=(scene.push, scene.cap),
            point_defence=2,
            overlay=scene.overlay.overlay,
            terrain=self._terrain,
        )
        return home, enemy

    def _add_runtime_logic(
        self,
        m: Mission,
        razor: FlyingGroup,
        packages: tuple[tuple[FlyingGroup, ...], ...],
    ) -> None:
        chooser = triggers.TriggerStart(comment="Choose runtime adversary package")
        chooser.add_action(action.SetFlagRandom(_PACKAGE_FLAG, 1, len(packages)))
        m.triggerrules.triggers.append(chooser)

        gate = m.triggers.add_triggerzone(
            position=self.at(*_PUSH),
            radius=9_000,
            hidden=True,
            name="Razor push gate",
        )
        for package_number, groups in enumerate(packages, start=1):
            self._arm_package_triggers(
                m,
                razor,
                gate.id,
                package_number=package_number,
                groups=groups,
            )

        calls = (
            "Magic: Razor, first hostile group is committing. Picture is developing; stand by for BRAA.",
            "Magic: Razor, new hostile group committing after the reset. Stand by for BRAA.",
            "Magic: Razor, another hostile group is inbound. Keep your fuel and weapons state in mind.",
            "Magic: Razor, fourth hostile group committing. Do not chase contacts south toward Kabul.",
            "Magic: Razor, final hostile group is airborne and committing. Clear it to finish the sweep.",
        )
        for wave_number, text in enumerate(calls, start=1):
            mission_triggers.message_to_coalition(
                m,
                comment=f"Magic announces wave {wave_number}",
                conditions=(
                    condition.FlagEquals(_RELEASED_FLAG_BASE + wave_number, 1),
                ),
                voice=self._voice,
                text=text,
                seconds=18,
            )

        mission_triggers.intro(
            m,
            comment="Razor sweep brief",
            voice=self._voice,
            text=(
                "Magic: Razor, picture is clean for now. Push north-east and I "
                "will call each hostile commitment. Expect eight aircraft, but "
                "type and axis are uncertain."
            ),
        )
        mission_triggers.message_to_all(
            m,
            comment="Razor lost",
            conditions=(condition.GroupDead(razor.id),),
            voice=self._voice,
            text="Magic: Razor is down. The fighter sweep has failed.",
            seconds=20,
        )

    def _arm_package_triggers(
        self,
        m: Mission,
        razor: FlyingGroup,
        gate_id: int,
        *,
        package_number: int,
        groups: tuple[FlyingGroup, ...],
    ) -> None:
        for wave_number, group in enumerate(groups, start=1):
            release = triggers.TriggerOnce(
                comment=f"Release package {package_number} wave {wave_number}"
            )
            release.add_condition(condition.FlagEquals(_PACKAGE_FLAG, package_number))
            if wave_number == 1:
                release.add_condition(condition.PartOfGroupInZone(razor.id, gate_id))
            else:
                previous_flag = _CLEARED_FLAG_BASE + package_number * 10 + wave_number
                cleared = triggers.TriggerOnce(
                    comment=(f"Package {package_number} wave {wave_number - 1} cleared")
                )
                cleared.add_condition(condition.GroupDead(groups[wave_number - 2].id))
                cleared.add_action(action.SetFlag(previous_flag))
                m.triggerrules.triggers.append(cleared)
                release.add_condition(
                    condition.TimeSinceFlag(previous_flag, _WAVE_RESET_S)
                )
            release.add_action(action.ActivateGroup(group.id))
            release.add_action(action.SetFlag(_RELEASED_FLAG_BASE + wave_number))
            m.triggerrules.triggers.append(release)

        victory = tuple(condition.GroupDead(group.id) for group in groups)
        mission_triggers.message_to_all(
            m,
            comment=f"Package {package_number} destroyed",
            conditions=(
                condition.FlagEquals(_PACKAGE_FLAG, package_number),
                *victory,
            ),
            voice=self._voice,
            text=(
                "Magic: Razor, hostile fighter package is destroyed. The Bagram "
                "corridor is clear; sweep complete, recover at Bagram."
            ),
            seconds=25,
        )

    @staticmethod
    def _draw_plan(
        plan: PlanOverlay,
        scene: _Scene,
        magic_track: tuple[Point, Point],
        home: sanc.Sanctuary,
        enemy: sanc.Sanctuary,
    ) -> list:
        home.draw(plan)
        briefed = enemy.draw(plan)
        plan.route(
            (
                scene.bagram.position,
                scene.push,
                scene.cap,
                scene.egress,
                scene.bagram.position,
            ),
            label="RAZOR SWEEP",
        )
        plan.orbit(*magic_track, label="MAGIC 251.000 AM")
        plan.waypoint_label(scene.cap, "RAZOR CAP BOX")
        plan.threat_area(scene.cap, 72_000, "VARIABLE FIGHTER CORRIDORS")
        return briefed

    def _in_game_briefing(self) -> str:
        return f"""BAGRAM WILDCARD — Afghanistan, 23 October 2026, 10:20 local
===============================================================
MISSION
  Razor launches hot from Bagram for a fighter sweep north-east of the field.
  Overnight collection indicates a Russian composite package of eight aircraft
  dispersed among several corridors. Composition, group size,
  missile fit, pilot quality and approach direction are unresolved.

EXECUTION
  BAGRAM → PUSH → CAP → EGRESS → BAGRAM
  Magic will call each commitment. Groups are expected to arrive separately,
  with a short reset between fights. Destroy every committed aircraft to clear
  the corridor; there is no ground target.

LOADOUT
{self.loadout_brief("Razor", _HORNET_FITS)}
  Both aircraft carry the same fit: ten AIM-120C, two AIM-9X and one centerline
  tank. Lead is the player; Razor two is an Excellent (Ace-level) AI wingman.

CONTROL / ROE
  Magic E-3A: {_MAGIC_FREQUENCY_MHZ}.000 AM, already airborne west of Bagram.
  Engage aircraft declared hostile by Magic. Do not pursue south over Kabul;
  an SA-3 and point defence protect the enemy recovery field.

FALL-BACK
  Bagram shield's cyan NASAMS ring is friendly sanctuary. If damaged, Winchester
  or low on fuel, drag west into that envelope and recover at Bagram.
"""

    def readme(self) -> str:
        return f"""# {self.title}

## Mission

Launch **hot** from **Bagram** as one player F/A-18C lead with one **Excellent
(Ace-level) AI wingman**. Magic is already airborne west of Bagram on
**{_MAGIC_FREQUENCY_MHZ}.000 AM**.

Crossing the push line commits one of **eight adversary packages selected by DCS
at mission runtime**. The same `.miz` therefore plays differently on repeat
sorties. Every package contains exactly **eight aircraft**, delivered in five
spaced waves of one to three aircraft; aircraft type, approach axis, missile
fit and pilot quality vary. The range runs from an all-MiG-23 package to an
all-Su-33 package, with MiG-29A/S, Su-27 and Su-34 mixtures between them.

## Razor

One human lead and one AI wingman fly identical fits:

{self.loadout_table("Razor", _HORNET_FITS)}

Each Hornet has **ten AIM-120Cs**, **two AIM-9Xs**, and one **330-gallon
centerline tank**. The dual AMRAAM racks occupy stations 2/3/7/8, the single
AMRAAMs stations 4/6, the tank station 5, and the AIM-9Xs the wingtips.

## Objective and boundaries

```text
BAGRAM → PUSH → CAP → EGRESS → BAGRAM
```

Destroy all eight committed aircraft. Magic announces when the fighter corridor
is clear. The next group does not release until the current one has been
destroyed and the 75-second reset has elapsed.

The cyan **Bagram NASAMS** ring is friendly sanctuary. Do not pursue contacts
south over **Kabul**: its recovery field is protected by an SA-3 and point
defence. The F10 plan shows the broad corridor assessment, not the hidden
runtime-selected spawn points.

## Re-generate

```bash
uv run dcs-mission-creator generate {self.name} --output-dir out/{self.name}
```
"""


def main() -> None:
    run_cli(BagramWildcard)


if __name__ == "__main__":
    main()
