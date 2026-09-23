"""Afghanistan ``Panjshir Blackout`` — single-player Hornet strike through an IADS.

Razor is one player-flown F/A-18C with an AI wingman, hot at Bagram.  The
target is a pair of hardened bunkers housing the Russian ``Grom`` integrated
air-defence command node in the upper Panjshir valley.  An S-300PS, two mobile
Buk batteries, two Tor sections and a two-radar early-warning chain are wired
through Skynet-IADS.  The batteries remain dark until cued, react to HARM fire,
and the Buks displace after emitting.

The direct high route is inside every long-range envelope.  The published
route is a terrain-checked, low-level corridor: at its planned AGL profile all
three long-range sites are masked at every point.  The player carries two
HARMs and two penetrator JDAMs; the AI wingman carries four HARMs and can be
sent after air defences through the normal wingman radio menu.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from dcs import condition, planes, statics, task, templates, vehicles
from dcs.country import Country
from dcs.drawing.icon import StandardIcon
from dcs.mapping import LatLng, Point
from dcs.mission import Mission, StartType
from dcs.terrain.afghanistan.afghanistan import Afghanistan
from dcs.terrain.terrain import Airport
from dcs.unit import Skill
from dcs.unitgroup import FlyingGroup, VehicleGroup

from dcs_mission_creator.core import (
    air_defense as ad,
    dtc,
    loadout,
    sanctuary as sanc,
    triggers as mission_triggers,
    waypoints,
)
from dcs_mission_creator.core.cli import run_cli
from dcs_mission_creator.core.difficulty import Difficulty
from dcs_mission_creator.core.iads import Listener, Site, arm_iads
from dcs_mission_creator.core.loadout import Loadout
from dcs_mission_creator.core.map_draw import PlanOverlay
from dcs_mission_creator.core.mission_builder import Assembled, MissionBuilder
from dcs_mission_creator.core.mission_kit import offset
from dcs_mission_creator.core.placement import load_scene
from dcs_mission_creator.core.waypoints import Leg
from dcs_mission_creator.core.weather import Weather, Wind
from dcs_mission_creator.map_overlay.scene import TacticalScene

# Positions selected with ``survey afghanistan``.  The target and every site
# centre are clear ground; the wide templates are snapped against the overlay
# after dispersion so their individual vehicles do not land in canopy/water.
_TARGET = (35.3986, 69.6965)
_SA10 = (35.2141, 69.7553)
_BUK_SOUTH = (35.2492, 69.7467)
_BUK_NORTH = (35.4518, 69.7026)
_EWR_SOUTH = (35.2931, 69.7339)
_EWR_NORTH = (35.4717, 69.6273)

_SA10_RING_M = 90_000.0
_BUK_RING_M = 45_000.0
_TOR_RING_M = 12_000.0
_ROUTE_SPEED_KPH = 700.0
_ROUTE_CLEARANCE_M = 150.0
_MAGIC_FREQUENCY_MHZ = 251

# Produced by the valley planner with a 4 km minimum leg.  The values are AGL,
# not pydcs altitudes; ``waypoints.agl_profile`` converts them to AMSL and
# checks every straight segment against the 50 m elevation raster.
_LOW_ROUTE = (
    ("LOW GATE", 34.9588, 69.2754, 350.0),
    ("PUSH", 35.1900, 69.2880, 350.0),
    ("WEST BEND", 35.2090, 69.3060, 350.0),
    ("NORTH BEND", 35.2280, 69.3320, 350.0),
    ("VALLEY ONE", 35.2500, 69.4320, 350.0),
    ("SADDLE", 35.2620, 69.4580, 550.0),
    ("VALLEY TWO", 35.2810, 69.4840, 350.0),
    ("PANJSHIR", 35.3190, 69.5280, 550.0),
    ("NARROWS", 35.3500, 69.5800, 350.0),
    ("IP", 35.3610, 69.6220, 550.0),
)

_LEAD_FIT = Loadout(
    role="HARM / GBU-31(V)4",
    carries=(
        "two AGM-88C HARMs, two GBU-31(V)4/B penetrator JDAMs, ATFLIR, "
        "one 330 gal tank, two AIM-9X and one AIM-120C"
    ),
    stores=(
        (1, "AIM_9X_Sidewinder_IR_AAM"),
        (2, "AGM_88C_HARM___High_Speed_Anti_Radiation_Missile_"),
        (3, "GBU_31_V_4_B___JDAM__2000lb_GPS_Guided_Penetrator_Bomb"),
        (4, "AN_ASQ_228_ATFLIR___Targeting_Pod"),
        (5, "FPU_8A_Fuel_Tank_330_gallons"),
        (6, "AIM_120C_AMRAAM___Active_Radar_AAM"),
        (7, "GBU_31_V_4_B___JDAM__2000lb_GPS_Guided_Penetrator_Bomb"),
        (8, "AGM_88C_HARM___High_Speed_Anti_Radiation_Missile_"),
        (9, "AIM_9X_Sidewinder_IR_AAM"),
    ),
)

_WINGMAN_FIT = Loadout(
    role="AGM-88C x4",
    carries=(
        "four AGM-88C HARMs, one 330 gal tank, two AIM-9X and one AIM-120C"
    ),
    stores=(
        (1, "AIM_9X_Sidewinder_IR_AAM"),
        (2, "AGM_88C_HARM___High_Speed_Anti_Radiation_Missile_"),
        (3, "AGM_88C_HARM___High_Speed_Anti_Radiation_Missile_"),
        (5, "FPU_8A_Fuel_Tank_330_gallons"),
        (6, "AIM_120C_AMRAAM___Active_Radar_AAM"),
        (7, "AGM_88C_HARM___High_Speed_Anti_Radiation_Missile_"),
        (8, "AGM_88C_HARM___High_Speed_Anti_Radiation_Missile_"),
        (9, "AIM_9X_Sidewinder_IR_AAM"),
    ),
)
_FITS = (_LEAD_FIT, _WINGMAN_FIT)


@dataclass(frozen=True)
class _Scene:
    bagram: Airport
    target: Point
    sa10: Point
    buk_south: Point
    buk_north: Point
    ewr_south: Point
    ewr_north: Point
    corridor: tuple[Leg, ...]
    overlay: TacticalScene


@dataclass(frozen=True)
class _RedForces:
    sa10: VehicleGroup
    buk_south: VehicleGroup
    buk_north: VehicleGroup
    target_tor: VehicleGroup
    sa10_tor: VehicleGroup
    ewrs: tuple[VehicleGroup, ...]
    bunkers: tuple


class PanjshirBlackout(MissionBuilder):
    """A fixed single-player two-ship: one human lead and one AI wingman."""

    name = "panjshir_blackout"
    title = "Panjshir Blackout"
    difficulty = Difficulty.VETERAN
    terrain = Afghanistan
    blue_task = (
        "Fly Razor's terrain-masked Panjshir ingress, suppress the Russian IADS, "
        "destroy both hardened Grom command bunkers, and recover at Bagram."
    )
    red_task = (
        "Use the early-warning chain to cue the S-300PS, Buk and Tor batteries; "
        "protect the Grom command node and survive anti-radiation attack."
    )
    start_time = datetime(2026, 10, 21, 6, 40, tzinfo=timezone.utc)
    weather = Weather(
        name="Cold clear Panjshir dawn",
        season_temperature=9,
        clouds_base=5_500,
        clouds_thickness=500,
        clouds_density=2,
        visibility_distance=45_000,
        wind_at_ground=Wind(direction=300, speed=2),
        wind_at_2000=Wind(direction=310, speed=6),
        wind_at_8000=Wind(direction=320, speed=14),
    )

    def __init__(self, *, players: int = 2) -> None:
        if players != 2:
            raise ValueError(
                "panjshir_blackout is a fixed single-player mission: "
                "one human lead plus one AI wingman"
            )
        super().__init__(players=2)

    def _assemble(self, m: Mission, plan: PlanOverlay) -> Assembled:
        scene = self._scene()
        scene.bagram.set_blue()
        russia = m.country("Russia")
        usa = m.country("USA")

        red = self._spawn_red(m, russia, scene)
        magic = self._spawn_magic(m, usa, scene)
        razor = self._spawn_razor(m, usa, scene, red.bunkers)
        home = self._spawn_home_defence(m, usa, scene)

        self._arm_network(m, red, magic)
        self._add_triggers(m, razor, red.bunkers)
        briefed = self._draw_plan(plan, scene, red, home)
        return Assembled(scene.overlay.overlay, briefed)

    def _scene(self) -> _Scene:
        t = self._terrain
        return _Scene(
            bagram=t.airports["Bagram"],
            target=self.at(*_TARGET),
            sa10=self.at(*_SA10),
            buk_south=self.at(*_BUK_SOUTH),
            buk_north=self.at(*_BUK_NORTH),
            ewr_south=self.at(*_EWR_SOUTH),
            ewr_north=self.at(*_EWR_NORTH),
            corridor=tuple(
                Leg(name, Point.from_latlng(LatLng(lat, lon), t), agl)
                for name, lat, lon, agl in _LOW_ROUTE
            ),
            overlay=load_scene("afghanistan"),
        )

    def _spawn_red(
        self, m: Mission, russia: Country, scene: _Scene
    ) -> _RedForces:
        """Build the two belts, their point defence, EWR chain and objective."""
        ov = scene.overlay.overlay
        sa10 = templates.VehicleTemplate.Russia.sa10_site(
            m,
            scene.sa10,
            300,
            prefix="Grumble south ",
            skill=Skill.Excellent,
        )
        ad.disperse_site(sa10, radius_m=550.0, overlay=ov, terrain=self._terrain)

        buk_south = self._buk(m, russia, scene.buk_south, "Gadfly south ", scene)
        buk_north = self._buk(m, russia, scene.buk_north, "Gadfly north ", scene)

        target_tor = ad.build_sa15_site(
            m,
            russia,
            self.at(35.3989, 69.6999),
            270,
            launchers=2,
            prefix="Grom point defence ",
            skill=Skill.Excellent,
            overlay=ov,
            terrain=self._terrain,
        )
        sa10_tor = ad.build_sa15_site(
            m,
            russia,
            offset(scene.sa10, east_m=-1_200, north_m=700),
            300,
            launchers=2,
            prefix="Grumble point defence ",
            skill=Skill.High,
            overlay=ov,
            terrain=self._terrain,
        )
        ewrs = tuple(
            ad.build_ewr_chain(
                m,
                russia,
                (scene.ewr_south, scene.ewr_north),
                prefix="Panjshir EWR",
                heading=270,
                skill=Skill.Excellent,
            )
        )
        bunkers = self._spawn_command_node(m, russia, scene.target)
        return _RedForces(
            sa10,
            buk_south,
            buk_north,
            target_tor,
            sa10_tor,
            ewrs,
            bunkers,
        )

    def _buk(
        self,
        m: Mission,
        russia: Country,
        position: Point,
        prefix: str,
        scene: _Scene,
    ) -> VehicleGroup:
        buk = templates.VehicleTemplate.sa11_site(
            m,
            russia,
            position,
            heading=270,
            prefix=prefix,
            skill=Skill.Excellent,
        )
        # The stock template includes a rifleman.  Leaving him in the group
        # reduces the whole mobile battery to walking speed and defeats the
        # shoot-and-scoot behavior configured below.
        buk.units = [
            u for u in buk.units if u.type != vehicles.Infantry.Infantry_AK.id
        ]
        return ad.disperse_site(
            buk,
            radius_m=420.0,
            overlay=scene.overlay.overlay,
            terrain=self._terrain,
        )

    @staticmethod
    def _spawn_command_node(m: Mission, russia: Country, target: Point) -> tuple:
        bunkers = (
            m.static_group(
                russia,
                "Grom operations bunker",
                statics.Fortification.Fire_Control_Bunker,
                position=target,
                heading=250,
            ),
            m.static_group(
                russia,
                "Grom communications bunker",
                statics.Fortification.Fire_Control_Bunker,
                position=offset(target, east_m=140, north_m=80),
                heading=250,
            ),
        )
        m.static_group(
            russia,
            "Grom generator",
            statics.Fortification.GeneratorF,
            position=offset(target, east_m=230, north_m=35),
            heading=250,
        )
        m.static_group(
            russia,
            "Grom stores",
            statics.Fortification.Cargo02,
            position=offset(target, east_m=-120, north_m=100),
            heading=70,
        )
        return bunkers

    @staticmethod
    def _spawn_magic(m: Mission, usa: Country, scene: _Scene) -> FlyingGroup:
        """Magic is the ESM listener that makes the IADS state calls."""
        return m.awacs_flight(
            usa,
            "Magic",
            planes.E_3A,
            airport=None,
            position=offset(scene.bagram.position, east_m=-35_000, north_m=-20_000),
            race_distance=80_000,
            heading=0,
            altitude=9_000,
            speed=740,
            frequency=_MAGIC_FREQUENCY_MHZ,
        )

    def _spawn_razor(
        self,
        m: Mission,
        usa: Country,
        scene: _Scene,
        bunkers: tuple,
    ) -> FlyingGroup:
        """One Player lead and one High-skill AI wingman in the same group."""
        razor = m.flight_group_from_airport(
            country=usa,
            name="Razor",
            aircraft_type=planes.FA_18C_hornet,
            airport=scene.bagram,
            maintask=task.SEAD,
            start_type=StartType.Warm,
            group_size=2,
        )
        razor.units[0].skill = Skill.Player
        razor.units[1].skill = Skill.High
        loadout.arm_unit(razor.units[0], planes.FA_18C_hornet, _LEAD_FIT.stores)
        loadout.arm_unit(razor.units[1], planes.FA_18C_hornet, _WINGMAN_FIT.stores)
        loadout.record(m, "Razor", _FITS)

        profile = waypoints.agl_profile(
            scene.corridor,
            scene.overlay.overlay,
            clearance_m=_ROUTE_CLEARANCE_M,
        )
        razor.add_runway_waypoint(scene.bagram)
        for leg, altitude in profile:
            razor.add_waypoint(
                leg.position,
                altitude=altitude,
                speed=_ROUTE_SPEED_KPH,
                name=leg.name,
            )
        waypoints.add_target_waypoint(
            razor,
            bunkers[0],
            overlay=scene.overlay.overlay,
            speed=_ROUTE_SPEED_KPH,
            name="OPS BUNKER — AIMPOINT",
        )
        waypoints.add_target_waypoint(
            razor,
            bunkers[1],
            overlay=scene.overlay.overlay,
            speed=_ROUTE_SPEED_KPH,
            name="COMMS BUNKER — AIMPOINT",
        )
        # LOW GATE sits on Bagram itself; the landing gate already supplies the
        # same final position, so repeating it on egress only spends the 26th
        # navigation point in a 25-point budget.
        for leg, altitude in reversed(profile[1:]):
            razor.add_waypoint(
                leg.position,
                altitude=altitude,
                speed=_ROUTE_SPEED_KPH,
                name=f"EGRESS {leg.name}",
            )
        razor.add_runway_waypoint(scene.bagram)
        razor.land_at(scene.bagram)
        return razor

    def _spawn_home_defence(
        self, m: Mission, usa: Country, scene: _Scene
    ) -> sanc.Sanctuary:
        return sanc.build_sanctuary(
            m,
            usa,
            scene.bagram,
            callsign="Bagram shield",
            facing=scene.target,
            battery=sanc.NASAMS,
            keep_clear=[scene.target, scene.sa10, scene.buk_south, scene.buk_north],
            point_defence=2,
            overlay=scene.overlay.overlay,
            terrain=self._terrain,
        )

    def _arm_network(
        self, m: Mission, red: _RedForces, magic: FlyingGroup
    ) -> None:
        """Wire every radar-guided battery into one cued, HARM-reactive net."""
        sites = [
            Site(
                red.sa10,
                "SA-10 Grumble",
                go_live_percent=160,
                point_defence=red.sa10_tor,
                probability=0.92,
                delay_s=(18.0, 42.0),
                shutdown_s=(280.0, 420.0),
                react_range_m=90_000.0,
                net_relay=0.75,
            ),
            Site(
                red.buk_south,
                "southern SA-11 Gadfly",
                go_live_percent=150,
                probability=0.92,
                delay_s=(12.0, 32.0),
                shutdown_s=(240.0, 360.0),
                react_range_m=75_000.0,
                net_relay=0.70,
                scoot_after_s=35.0,
            ),
            Site(
                red.buk_north,
                "unfixed northern SA-11 Gadfly",
                go_live_percent=125,
                probability=0.94,
                delay_s=(10.0, 28.0),
                shutdown_s=(240.0, 360.0),
                react_range_m=75_000.0,
                net_relay=0.65,
                scoot_after_s=30.0,
            ),
            Site(
                red.target_tor,
                "Grom SA-15 point defence",
                go_live_percent=130,
                probability=0.90,
                delay_s=(8.0, 24.0),
                shutdown_s=(180.0, 300.0),
                react_range_m=35_000.0,
                net_relay=0.80,
                jockey_m=0.0,
            ),
            Site(
                red.sa10_tor,
                "Grumble SA-15 point defence",
                go_live_percent=140,
                probability=0.90,
                delay_s=(8.0, 24.0),
                shutdown_s=(180.0, 300.0),
                react_range_m=35_000.0,
                net_relay=0.80,
                jockey_m=0.0,
            ),
            *[
                Site(
                    ewr,
                    f"early-warning radar {i}",
                    role="ewr",
                    probability=0.70,
                    delay_s=(35.0, 85.0),
                    shutdown_s=(180.0, 280.0),
                    react_range_m=100_000.0,
                    net_relay=0.60,
                )
                for i, ewr in enumerate(red.ewrs, start=1)
            ],
        ]
        arm_iads(
            m,
            sites,
            listeners=(Listener(magic, "Magic"),),
            voice=self._voice,
            coalition="blue",
            name="Panjshir Russian IADS",
            down_call="Magic: {label} has ceased emissions; site is dark.",
            up_call="Magic: {label} is radiating again; expect it hot.",
            trace=True,
            debug=False,
        )

    def _draw_plan(
        self,
        plan: PlanOverlay,
        scene: _Scene,
        red: _RedForces,
        home: sanc.Sanctuary,
    ) -> list[dtc.ThreatPoint]:
        home.draw(plan)
        route = [leg.position for leg in scene.corridor]
        route += [group.units[0].position for group in red.bunkers]
        route += [leg.position for leg in reversed(scene.corridor)]
        plan.route(route, "Razor low-level corridor")
        plan.objective(scene.target, "GROM IADS COMMAND NODE", radius=3_000.0)
        plan.waypoint_label(red.bunkers[0].units[0].position, "OPS BUNKER")
        plan.waypoint_label(red.bunkers[1].units[0].position, "COMMS BUNKER")

        briefed = [
            *dtc.briefed(
                plan.threat(
                    scene.sa10,
                    radius=_SA10_RING_M,
                    label="SA-10 Grumble",
                    icon=StandardIcon.AirDefense,
                ),
                dtc.SA_10,
                label="SA-10",
            ),
            *dtc.briefed(
                plan.threat(
                    scene.buk_south,
                    radius=_BUK_RING_M,
                    label="SA-11 Gadfly south",
                    icon=StandardIcon.AirDefense,
                ),
                dtc.SA_11,
                label="SA-11 south",
            ),
            *dtc.briefed(
                plan.threat(
                    red.target_tor.units[0].position,
                    radius=_TOR_RING_M,
                    label="SA-15 at Grom",
                    icon=StandardIcon.AirDefense,
                ),
                dtc.SA_15,
                label="SA-15 Grom",
            ),
        ]
        # The northern Buk was heard by ELINT but not fixed, so putting a ring
        # on it would disclose information the briefing explicitly withholds.
        for pos, label in (
            (scene.ewr_south, "EWR south"),
            (scene.ewr_north, "EWR north"),
        ):
            plan.threat(pos, radius=4_000.0, label=label, icon=StandardIcon.SearchRadar)
        return briefed

    def _add_triggers(
        self, m: Mission, razor: FlyingGroup, bunkers: tuple
    ) -> None:
        mission_triggers.intro(
            m,
            comment="Razor mission brief",
            voice=self._voice,
            text=(
                "Magic: Razor, Grom is active. Stay in the Panjshir corridor; "
                "the long-range batteries are networked and expected dark. "
                "Your wingman carries four HARMs."
            ),
        )
        mission_triggers.message_to_all(
            m,
            comment="Grom command node destroyed",
            conditions=tuple(condition.UnitDead(g.units[0].id) for g in bunkers),
            voice=self._voice,
            text=(
                "Magic: both Grom bunkers are destroyed. The Panjshir command "
                "node is down. Razor, reverse the valley route and recover Bagram."
            ),
            seconds=25,
        )
        mission_triggers.message_to_all(
            m,
            comment="Razor lost before Grom destroyed",
            conditions=(
                condition.GroupDead(razor.id),
                condition.UnitAlive(bunkers[0].units[0].id),
                condition.UnitAlive(bunkers[1].units[0].id),
            ),
            voice=self._voice,
            text=(
                "Magic: Razor is down and Grom remains operational. Abort the raid."
            ),
            seconds=20,
        )

    def _in_game_briefing(self) -> str:
        distance_km = round(
            self.at(*_TARGET).distance_to_point(
                self._terrain.airports["Bagram"].position
            )
            / 1000
        )
        return f"""PANJSHIR BLACKOUT — Afghanistan, 21 October 2026, 06:40 local
====================================================================
MISSION
  Razor is a fixed two-ship: you are the F/A-18C lead and Razor 2 is a
  High-skill AI wingman in the same group. Grom is {distance_km} km from
  Bagram as the crow flies. Use the surveyed Panjshir corridor and destroy
  both hardened command bunkers.

INTELLIGENCE
  Six-hour satellite imagery fixes the SA-10, southern SA-11, EWR chain and
  Grom point defence shown on the map. A northern SA-11 was heard by ELINT
  ninety minutes ago but never fixed; it has no ring. Expect batteries to stay
  dark until the EWR chain cues them, and expect the Buks to move after emitting.

EXECUTION
  Remain on the low route through IP. The surveyed profile is masked from all
  three long-range batteries at every published corridor point. Terrain mask
  ends on the terminal run. Use your HARMs to buy a dark window, or order
  Razor 2 to ENGAGE AIR DEFENCES; then attack OPS BUNKER and COMMS BUNKER with
  one GBU-31(V)4/B each. Reverse the corridor after release.

LOADOUT
  #1 Razor Pilot #1 — PLAYER — {_LEAD_FIT.carries}
  #2 Razor Pilot #2 — AI WINGMAN — {_WINGMAN_FIT.carries}

COMMS
  Magic: {_MAGIC_FREQUENCY_MHZ}.000 AM. Bagram ATC is on the kneeboard.

SUCCESS
  Both hardened bunkers destroyed. SAM kills are optional; suppression is a
  valid way through. Recover at Bagram.
"""

    def readme(self) -> str:
        distance_km = round(
            self.at(*_TARGET).distance_to_point(
                self._terrain.airports["Bagram"].position
            )
            / 1000
        )
        return f"""# {self.title}

## Mission

This is a **single-player** F/A-18C mission. You fly Razor lead and a
High-skill AI wingman occupies Razor 2 in the same group, so the normal DCS
wingman radio commands work. Launch hot from Bagram and fly the terrain-masked
Panjshir corridor to the Russian Grom IADS command node, **{distance_km} km
straight-line from Bagram**, then destroy both hardened bunkers.

## The IADS

The mission loads the repository's Skynet-IADS integration and its first-party
MIST compatibility layer. Two 55G6 early-warning radars cue an SA-10, two
SA-11 batteries and two SA-15 sections. Sites sit dark until cued, can shut
down under observed HARM attack, and the mobile Buks shoot and scoot after
emitting. Magic is the friendly ESM listener; emission-state calls stop if he
cannot observe the site.

Six-hour satellite imagery fixes the drawn SA-10, southern Buk, EWRs and target
Tor. ELINT heard another Buk north of the target ninety minutes before takeoff
but did not fix it, so that battery deliberately has no F10 ring.

## Flight and weapons

| Jet | Crew | Role | Stores |
|-----|------|------|--------|
| Razor 1 | Player | {_LEAD_FIT.role} | {_LEAD_FIT.carries} |
| Razor 2 | AI wingman | {_WINGMAN_FIT.role} | {_WINGMAN_FIT.carries} |

Use the radio menu to order Razor 2 to **Engage Air Defences** when you want his
four HARMs committed. Your own two HARMs can kill a radar, but their more
important job is to force a dark window for the terminal run. Put one
GBU-31(V)4/B on **OPS BUNKER — AIMPOINT** and one on **COMMS BUNKER — AIMPOINT**.

## Route

The route was generated against the Afghanistan elevation raster and checked
at 150 m segment clearance. At the planned 350–550 m AGL profile, the SA-10
and both Buks are terrain-masked at every published low-level point. That mask
ends on the terminal run, where the target's Tor section is inside 12 km.

```text
BAGRAM → LOW GATE → PUSH → WEST BEND → NORTH BEND → VALLEY ONE →
SADDLE → VALLEY TWO → PANJSHIR → NARROWS → IP → GROM → reverse route → BAGRAM
```

Primary success is both Grom bunkers destroyed. Destroying SAM sites is
optional; surviving their network long enough to deliver the JDAMs is the task.

## Re-generate

```bash
uv run dcs-mission-creator generate {self.name} --output-dir out/{self.name}
```
"""


def main() -> None:
    run_cli(PanjshirBlackout)


if __name__ == "__main__":
    main()
