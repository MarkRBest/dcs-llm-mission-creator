"""Afghanistan ``Bagram Convoy Ambush`` — a strike that becomes an intercept.

Razor launches from Bagram to stop a small Russian-backed convoy before it
reaches the Panjshir-side villages.  Destroying the lead vehicle wakes a hidden
MANPADS team; destroying the convoy sends a MiG-29A alert pair out of Kabul.
The two events are intentionally separate: the first makes the bombing run
matter, and the second gives the AMRAAMs and AIM-9Xs a clear purpose on egress.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import cast

from dcs import action, condition, planes, task, triggers, vehicles
from dcs.country import Country
from dcs.mission import Mission, StartType
from dcs.point import PointAction
from dcs.terrain.afghanistan.afghanistan import Afghanistan
from dcs.terrain.terrain import Airport
from dcs.unit import Skill
from dcs.unitgroup import FlyingGroup, VehicleGroup
from dcs.unittype import VehicleType

from dcs_mission_creator.core.cli import run_cli
from dcs_mission_creator.core.difficulty import Difficulty
from dcs_mission_creator.core.loadout import Loadout
from dcs_mission_creator.core.map_draw import PlanOverlay
from dcs_mission_creator.core.mission_builder import Assembled, MissionBuilder
from dcs_mission_creator.core.mission_kit import arm, offset, player_flight, set_skill
from dcs_mission_creator.core.placement import load_scene
from dcs_mission_creator.core.tasking import apply_ai_difficulty, scramble_on_trigger
from dcs_mission_creator.core.weather import Weather, Wind
from dcs_mission_creator.map_overlay.scene import ConvoyRoute

_CONVOY_ORIGIN_LAT = 35.2000
_CONVOY_ORIGIN_LON = 69.4000
_CONVOY_DESTINATION_LAT = 35.2500
_CONVOY_DESTINATION_LON = 69.4500
_INGRESS_ALTITUDE_M = 5_500
_CRUISE_SPEED_KPH = 760
_MIG_ALTITUDE_M = 7_000
_MIG_SPEED_KPH = 900
_MAGIC_FREQUENCY_MHZ = 251

# The Hornet carries six AMRAAMs and two AIM-9Xs for the MiG-29 response, plus
# four Rockeyes for the moving convoy. No laser designation is required.
_HORNET_FIT = Loadout(
    role="ROCKEYE*4 + AIM-120C*6 + AIM-9X*2",
    carries=(
        "four Mk-20 Rockeye cluster bombs on BRU-33 racks, six AIM-120C, "
        "two AIM-9X, one 330 gal tank"
    ),
    stores=(
        (1, "AIM_9X_Sidewinder_IR_AAM"),
        (2, "LAU_115_2_LAU_127_AIM_120C"),
        (3, "BRU_33_with_2_x_Mk_20_Rockeye___490lbs_CBU__247_x_HEAT_Bomblets"),
        (4, "AIM_120C_AMRAAM___Active_Radar_AAM"),
        (5, "FPU_8A_Fuel_Tank_330_gallons"),
        (6, "AIM_120C_AMRAAM___Active_Radar_AAM"),
        (7, "BRU_33_with_2_x_Mk_20_Rockeye___490lbs_CBU__247_x_HEAT_Bomblets"),
        (8, "LAU_115_2_LAU_127_AIM_120C"),
        (9, "AIM_9X_Sidewinder_IR_AAM"),
    ),
)
# Both client slots fly the same complete mission; co-op divides the attacks,
# rather than making a beginner choose a specialised shooter or escort role.
_HORNET_FITS = (_HORNET_FIT, _HORNET_FIT)

_MIG_STORES = (
    (1, "R_73__AA_11_Archer____Infra_Red"),
    (2, "R_73__AA_11_Archer____Infra_Red"),
    (3, "R_27R__AA_10_Alamo_A____Semi_Act_Rdr"),
    (4, "Fuel_tank_1400L"),
    (5, "R_27R__AA_10_Alamo_A____Semi_Act_Rdr"),
    (6, "R_73__AA_11_Archer____Infra_Red"),
    (7, "R_73__AA_11_Archer____Infra_Red"),
)


class BagramConvoyAmbush(MissionBuilder):
    """Stop a road column, then survive the alert fighters it provokes."""

    name = "bagram_convoy_ambush"
    title = "Bagram Convoy Ambush"
    difficulty = Difficulty.TRAINED
    terrain = Afghanistan
    blue_task = (
        "Destroy the convoy before it reaches the Panjshir-side villages. "
        "Expect MANPADS after the lead vehicle is hit and a MiG-29A scramble "
        "from Kabul once the convoy is destroyed; recover at Bagram."
    )
    red_task = (
        "Move the supply convoy into the Panjshir foothills, defend it with a "
        "concealed MANPADS team, then scramble Kabul's MiG-29A alert pair."
    )
    start_time = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
    weather = Weather(
        name="Clear Bagram morning",
        season_temperature=17,
        clouds_base=4_500,
        clouds_thickness=350,
        clouds_density=1,
        visibility_distance=50_000,
        wind_at_ground=Wind(direction=310, speed=3),
        wind_at_2000=Wind(direction=320, speed=7),
        wind_at_8000=Wind(direction=330, speed=14),
    )

    def _assemble(self, m: Mission, plan: PlanOverlay) -> Assembled:
        """Build the convoy, its two reactions, and Razor's short sortie."""
        bagram = self._terrain.airports["Bagram"]
        kabul = self._terrain.airports["Kabul"]
        bagram.set_blue()
        kabul.set_red()
        scene = load_scene("afghanistan")
        convoy_route = scene.place_convoy_route(
            self.at(_CONVOY_ORIGIN_LAT, _CONVOY_ORIGIN_LON),
            self.at(_CONVOY_DESTINATION_LAT, _CONVOY_DESTINATION_LON),
        )

        usa, russia = m.country("USA"), m.country("Russia")
        convoy = self._spawn_convoy(m, russia, convoy_route)
        manpads = self._spawn_manpads(m, russia, convoy_route)
        migs = self._spawn_migs(m, russia, kabul, convoy_route.waypoints[0])
        self._spawn_magic(m, usa, bagram)
        self._spawn_player(m, usa, bagram, convoy_route)
        self._add_escalation_triggers(m, convoy, manpads, migs)
        self._draw_plan(plan, bagram, convoy_route)

        return Assembled(scene.overlay)

    def _spawn_convoy(
        self, m: Mission, russia: Country, route: ConvoyRoute
    ) -> VehicleGroup:
        """A six-vehicle road column whose destruction is the mission's frag."""
        convoy_types = cast(
            list[type[VehicleType]],
            [
                vehicles.Armor.BTR_80,
                vehicles.Unarmed.KAMAZ_Truck,
                vehicles.Unarmed.KAMAZ_Truck,
                vehicles.Unarmed.Ural_375,
                vehicles.Unarmed.KAMAZ_Truck,
                vehicles.Armor.BTR_80,
            ],
        )
        convoy = m.vehicle_group_platoon(
            russia,
            "Panjshir convoy",
            convoy_types,
            position=route.waypoints[0],
            heading=int(route.waypoints[0].heading_between_point(route.waypoints[1])),
            move_formation=PointAction.OnRoad,
        )
        convoy.add_waypoint(
            route.waypoints[1],
            move_formation=PointAction.OnRoad,
            speed=35,
        )
        set_skill(convoy, Skill.Average)
        apply_ai_difficulty(convoy, self.difficulty)
        return convoy

    def _spawn_manpads(
        self,
        m: Mission,
        russia: Country,
        route: ConvoyRoute,
    ) -> VehicleGroup:
        """A hidden Igla team that activates only after the lead vehicle dies."""
        # The convoy endpoints are snapped to a surveyed road by
        # `TacticalScene.place_convoy_route`; this small offset keeps the team
        # off that road without treating a hand-picked world coordinate as a
        # terrain fact.
        position = offset(route.waypoints[0], east_m=350, north_m=250)
        manpads = m.vehicle_group(
            russia,
            "Panjshir MANPADS",
            vehicles.AirDefence.SA_18_Igla_manpad,
            position=position,
            heading=int(position.heading_between_point(route.waypoints[0])),
            group_size=3,
            formation=VehicleGroup.Formation.Scattered,
        )
        set_skill(manpads, Skill.Average)
        manpads.late_activation = True
        return manpads

    def _spawn_migs(
        self, m: Mission, russia: Country, kabul: Airport, convoy_start
    ) -> FlyingGroup:
        """Kabul's two-ship MiG-29A alert section, cold until the convoy dies."""
        migs = m.flight_group_from_airport(
            country=russia,
            name="Viper",
            aircraft_type=planes.MiG_29A,
            airport=kabul,
            maintask=task.CAP,
            # `scramble_on_trigger` pushes DCS's engine-start command. The
            # alert pair must therefore be a cold-ramp group; a hot-ramp group
            # can ignore the uncontrolled hold and launch at mission start.
            start_type=StartType.Cold,
            group_size=2,
        )
        migs.add_runway_waypoint(kabul)
        # A CAP maintask alone does not make this a reacting intercept flight:
        # give the alert pair the same air-engagement task that pydcs's
        # `intercept_flight` helper installs.  Otherwise the pair can launch
        # on the trigger, fly its route, and never commit to Razor.
        migs.points[0].tasks[0] = task.EngageTargets(90_000, [task.Targets.All.Air])
        intercept = offset(convoy_start, east_m=-8_000, north_m=-5_000)
        migs.add_waypoint(
            intercept,
            altitude=_MIG_ALTITUDE_M,
            speed=_MIG_SPEED_KPH,
            name="INTERCEPT",
        )
        migs.add_runway_waypoint(kabul)
        migs.land_at(kabul)
        arm(migs, planes.MiG_29A, _MIG_STORES)
        set_skill(migs, Skill.Average)
        apply_ai_difficulty(migs, self.difficulty)
        return migs

    def _spawn_magic(self, m: Mission, usa: Country, bagram: Airport) -> None:
        """Magic E-3A already on station west of Bagram, watching the route."""
        m.awacs_flight(
            usa,
            "Magic",
            planes.E_3A,
            airport=None,
            position=offset(bagram.position, east_m=-25_000, north_m=-15_000),
            race_distance=70_000,
            heading=90,
            altitude=8_500,
            speed=740,
            frequency=_MAGIC_FREQUENCY_MHZ,
        )

    def _spawn_player(
        self, m: Mission, usa: Country, bagram: Airport, route: ConvoyRoute
    ) -> list[FlyingGroup]:
        """Razor Hornets fly Bagram → convoy route → Bagram with both magazines."""
        sections = player_flight(
            m,
            country=usa,
            name="Razor",
            aircraft_type=planes.FA_18C_hornet,
            airport=bagram,
            maintask=task.CAS,
            start_type=StartType.Warm,
            slots=self.players,
            loadouts=_HORNET_FITS,
        )
        attack = offset(route.waypoints[0], east_m=-4_000, north_m=-4_000)
        egress = offset(route.waypoints[1], east_m=-12_000, north_m=-7_000)
        for hornet in sections:
            hornet.add_runway_waypoint(bagram)
            hornet.add_waypoint(
                attack,
                altitude=_INGRESS_ALTITUDE_M,
                speed=_CRUISE_SPEED_KPH,
                name="PUSH",
            )
            hornet.add_waypoint(
                route.waypoints[0],
                altitude=_INGRESS_ALTITUDE_M,
                speed=700,
                name="CONVOY",
            )
            hornet.add_waypoint(
                egress,
                altitude=_INGRESS_ALTITUDE_M,
                speed=_CRUISE_SPEED_KPH,
                name="EGRESS",
            )
            hornet.add_runway_waypoint(bagram)
            hornet.land_at(bagram)
        return sections

    def _add_escalation_triggers(
        self, m: Mission, convoy: VehicleGroup, manpads: VehicleGroup, migs: FlyingGroup
    ) -> None:
        """Activate the ambush on the lead kill and scramble MiGs on the frag."""
        lead = convoy.units[0].id
        manpads_trigger = triggers.TriggerOnce(comment="MANPADS activate on lead kill")
        manpads_trigger.add_condition(condition.UnitDead(lead))
        manpads_trigger.add_action(action.ActivateGroup(manpads.id))
        m.triggerrules.triggers.append(manpads_trigger)
        self._message(
            m,
            comment="MANPADS warning",
            conditions=(condition.UnitDead(lead),),
            text=(
                "Magic: Razor, MANPADS launch reported near the convoy. Stay "
                "high, finish the frag, then egress west."
            ),
        )

        scramble_on_trigger(
            m,
            migs,
            condition.GroupDead(convoy.id),
            comment="Kabul MiG-29 scramble",
        )
        self._message(
            m,
            comment="MiG scramble warning",
            conditions=(condition.GroupDead(convoy.id),),
            text=(
                "Magic: Razor, Kabul has launched two MiG-29s. They are "
                "vectoring north-east toward your egress. AIM-120Cs and AIM-9Xs "
                "are available; defend yourselves and recover at Bagram."
            ),
            seconds=20,
        )
        self._message(
            m,
            comment="Convoy destroyed",
            conditions=(condition.GroupDead(convoy.id),),
            text=(
                "Magic: the convoy is destroyed. The villages are safe for "
                "now; expect the Kabul fighters and recover at Bagram when clear."
            ),
            seconds=15,
        )

    def _message(
        self, m: Mission, *, comment: str, conditions, text: str, seconds: int = 15
    ) -> None:
        """Send one matching text and voice call to the player coalition."""
        from dcs_mission_creator.core import triggers as mission_triggers

        mission_triggers.message_to_coalition(
            m,
            comment=comment,
            conditions=conditions,
            voice=self._voice,
            text=text,
            seconds=seconds,
        )

    @staticmethod
    def _draw_plan(plan: PlanOverlay, bagram: Airport, route: ConvoyRoute) -> None:
        """Show the route and last-known convoy area without freezing a moving unit."""
        plan.route((bagram.position, route.waypoints[0]), label="BAGRAM → CONVOY")
        plan.mobile_threat(route.waypoints[0], "CONVOY — LAST KNOWN")
        plan.waypoint_label(route.waypoints[1], "VILLAGE APPROACH")

    def _in_game_briefing(self) -> str:
        return f"""BAGRAM CONVOY AMBUSH — Afghanistan, 20 October 2026, 09:00 local
=================================================================
MISSION
  Razor launches hot from Bagram to destroy a six-vehicle convoy before it
  reaches the Panjshir-side villages. Its F10 mark is a last-known position;
  expect it to be moving north-east along the road.

THREATS
  A concealed SA-18 MANPADS team activates when the convoy lead is hit.
  Destroying the whole convoy triggers a two-ship MiG-29A scramble from Kabul.
  Magic E-3A is already on station west of Bagram on {_MAGIC_FREQUENCY_MHZ}.000 AM
  and will call the scramble.

LOADOUT
{self.loadout_brief("Razor", _HORNET_FITS)}
  The Hornets carry four Mk-20 Rockeyes, six AIM-120Cs, and two AIM-9Xs.
  No laser designation is required. The aircraft are hot on Bagram's ramp.

ROUTE
  BAGRAM → PUSH → CONVOY → EGRESS → BAGRAM
  Destroy the convoy with the cluster bombs, then use the radar/IR missiles to
  defend the egress if the MiGs press. The MiGs are a threat to survive, not a
  separate strike target.
"""

    def readme(self) -> str:
        return f"""# {self.title}

## Mission

Launch **hot** from **Bagram** and stop a six-vehicle convoy before it reaches
the Panjshir-side villages. The F10 marker is its last known location; the
column is moving north-east along the road.

{self.slot_summary("Razor")}. Every slot carries the complete strike and
self-defence fit:

{self.loadout_table("Razor", _HORNET_FITS)}

Visually locate the moving column and deliver the four **Mk-20 Rockeye** cluster
bombs; they need no laser code or self-lasing. The two **AIM-9Xs** are on the
wingtips, with six **AIM-120Cs** for the MiG response.

## Escalation

- Destroying the **lead vehicle** activates a concealed SA-18 MANPADS team.
- Destroying the **whole convoy** scrambles two MiG-29As from Kabul.
- **Magic** is already orbiting west of Bagram on **{_MAGIC_FREQUENCY_MHZ}.000 AM**
  and calls the scramble.

The convoy is the required target. The MiGs are the egress threat; fight them
only if they prevent a safe recovery at Bagram.

```text
BAGRAM → PUSH → CONVOY → EGRESS → BAGRAM
```

## Re-generate

```bash
uv run dcs-mission-creator generate {self.name} --output-dir out/{self.name}
```
"""


def main() -> None:
    run_cli(BagramConvoyAmbush)


if __name__ == "__main__":
    main()
