"""Caucasus "Operation Coastal Lantern" — broad-access multiplayer package.

The fictional Northern Directorate has occupied the Abkhaz coast and turned an
old coastal works into a command and logistics hub.  The Coastal Coalition can
attack it in several independent ways: CAP, SEAD, strike, road interdiction and
helicopter assault.  No one package gates another; a lightly coordinated public
server can still move the campaign forward while a well coordinated group can
make the routes considerably safer.

Every selectable module has eight client seats.  DCS limits one aircraft group
to four, so each module is one operational flight represented by a hot four-ship
and a cold four-ship at the same location.  Hornets and all three Tomcat variants
operate from two carriers in the Black Sea.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from dcs import (
    action,
    condition,
    helicopters,
    planes,
    ships,
    statics,
    task,
    templates,
    vehicles,
)
from dcs.country import Country
from dcs.drawing.icon import StandardIcon
from dcs.mapping import Point
from dcs.mission import Mission, StartType
from dcs.point import PointAction
from dcs.terrain.caucasus.caucasus import Caucasus
from dcs.terrain.terrain import Airport
from dcs.unit import Skill
from dcs.unitgroup import FlyingGroup, ShipGroup, StaticGroup, VehicleGroup

from dcs_mission_creator.core import (
    air_defense as ad,
    dtc,
    jtac,
    kneeboard,
    laser,
    triggers as mission_triggers,
)
from dcs_mission_creator.core.cli import run_cli
from dcs_mission_creator.core.difficulty import Difficulty
from dcs_mission_creator.core.iads import Listener, Site, arm_iads
from dcs_mission_creator.core.loadout import Loadout
from dcs_mission_creator.core.lua import InlineDoScript
from dcs_mission_creator.core.map_draw import PlanOverlay
from dcs_mission_creator.core.mission_builder import Assembled, MissionBuilder
from dcs_mission_creator.core.mission_kit import (
    offset,
    player_flight,
    player_flight_from_unit,
    set_skill,
)
from dcs_mission_creator.core.placement import (
    NO_FOREST,
    convoy_spawn,
    find_clear_spot,
    load_scene,
)
from dcs_mission_creator.core.tasking import (
    FacCallsign,
    apply_ai_difficulty,
    fac_attack_group,
)
from dcs_mission_creator.core.weather import Weather, Wind
from dcs_mission_creator.map_overlay.scene import TacticalScene

_SLOTS = 8
_STARTS = (StartType.Warm, StartType.Cold)
_SCORE_FLAG = 900
_SUCCESS_SCORE = 7
_JTAC_FREQ = 133
_LASER_CODE = 1688


def _fit(role: str, carries: str, *stores: tuple[int, str]) -> tuple[Loadout, ...]:
    """One explicitly checked fit, repeated across all eight seats."""
    return (Loadout(role=role, carries=carries, stores=stores),)


_F16 = _fit(
    "SEAD",
    "2 AIM-120C, 2 AIM-9X, 2 AGM-88C, 2 tanks, HTS, targeting pod, ECM",
    (1, "AIM_120C_AMRAAM___Active_Radar_AAM"),
    (2, "AIM_9X_Sidewinder_IR_AAM"),
    (3, "AGM_88C_HARM___High_Speed_Anti_Radiation_Missile_"),
    (4, "Fuel_tank_370_gal"),
    (5, "ALQ_184_Long"),
    (6, "Fuel_tank_370_gal"),
    (7, "AGM_88C_HARM___High_Speed_Anti_Radiation_Missile_"),
    (8, "AIM_9X_Sidewinder_IR_AAM"),
    (9, "AIM_120C_AMRAAM___Active_Radar_AAM"),
    (10, "AN_ASQ_213_HTS___HARM_Targeting_System"),
    (11, "AN_AAQ_28_LITENING___Targeting_Pod_"),
)

_HORNET = _fit(
    "Precision strike",
    "4 GBU-38, 4 GBU-12, 2 AIM-9X, AIM-120C, tank and ATFLIR",
    (1, "AIM_9X_Sidewinder_IR_AAM"),
    (2, "BRU_55_with_2_x_GBU_38___JDAM__500lb_GPS_Guided_Bomb"),
    (3, "BRU_33_with_2_x_GBU_12___500lb_Laser_Guided_Bomb"),
    (4, "AN_ASQ_228_ATFLIR___Targeting_Pod"),
    (5, "FPU_8A_Fuel_Tank_330_gallons"),
    (6, "AIM_120C_AMRAAM___Active_Radar_AAM"),
    (7, "BRU_33_with_2_x_GBU_12___500lb_Laser_Guided_Bomb"),
    (8, "BRU_55_with_2_x_GBU_38___JDAM__500lb_GPS_Guided_Bomb"),
    (9, "AIM_9X_Sidewinder_IR_AAM"),
)

_F15E = _fit(
    "Heavy strike",
    "4 GBU-12, 2 GBU-10, 2 AIM-120C, 2 AIM-9M, 2 tanks and LANTIRN",
    (1, "AIM_120C_AMRAAM___Active_Radar_AAM"),
    (2, "Fuel_tank_610_gal_"),
    (3, "AIM_9M_Sidewinder_IR_AAM"),
    (4, "GBU_12___4"),
    (7, "AN_AAQ_14_LANTIRN_TGT_Pod"),
    (9, "AN_AAQ_13_LANTIRN_NAV_POD"),
    (12, "GBU_10___2_"),
    (13, "AIM_9M_Sidewinder_IR_AAM"),
    (14, "Fuel_tank_610_gal_"),
    (15, "AIM_120C_AMRAAM___Active_Radar_AAM"),
)

_F15C = _fit(
    "CAP",
    "6 AIM-120, 2 AIM-9M and 3 tanks",
    (1, "AIM_120C_AMRAAM___Active_Radar_AAM"),
    (2, "Fuel_tank_610_gal"),
    (3, "AIM_9M_Sidewinder_IR_AAM"),
    (4, "AIM_120B_AMRAAM___Active_Radar_AAM"),
    (5, "AIM_120B_AMRAAM___Active_Radar_AAM"),
    (6, "Fuel_tank_610_gal"),
    (7, "AIM_120B_AMRAAM___Active_Radar_AAM"),
    (8, "AIM_120B_AMRAAM___Active_Radar_AAM"),
    (9, "AIM_9M_Sidewinder_IR_AAM"),
    (10, "Fuel_tank_610_gal"),
    (11, "AIM_120C_AMRAAM___Active_Radar_AAM"),
)

_A10 = _fit(
    "CAS",
    "4 Mavericks, 4 CBU-97, 4 CBU-87, AIM-9M, targeting pod and ECM",
    (1, "ALQ_184"),
    (3, "LAU_88_AGM_65H_2_L"),
    (4, "CBU_97___10_x_SFW_Cluster_Bomb"),
    (5, "CBU_87___202_x_CEM_Cluster_Bomb"),
    (7, "CBU_87___202_x_CEM_Cluster_Bomb"),
    (8, "CBU_97___10_x_SFW_Cluster_Bomb"),
    (9, "LAU_88___2_x_AGM_65D___Maverick_D__IIR_ASM__"),
    (10, "AN_AAQ_28_LITENING___Targeting_Pod_"),
    (11, "LAU_105___2_x_AIM_9M_Sidewinder_IR_AAM"),
)

_F14A = _fit(
    "Fleet CAP",
    "4 AIM-54A, 2 AIM-7M, 2 AIM-9M and 2 tanks",
    (1, "LAU_138_AIM_9M"),
    (2, "AIM_7M"),
    (3, "Fuel_tank_300_gal_"),
    (4, "AIM_54A_Mk47"),
    (5, "AIM_54A_Mk47"),
    (6, "AIM_54A_Mk47"),
    (7, "AIM_54A_Mk47"),
    (8, "Fuel_tank_300_gal_"),
    (9, "AIM_7M"),
    (10, "LAU_138_AIM_9M"),
)

_F14B = _fit(
    "Carrier strike",
    "2 GBU-12, AIM-7M, 2 AIM-9M, 2 tanks and LANTIRN",
    (1, "LAU_138_AIM_9M"),
    (2, "AIM_7M"),
    (3, "Fuel_tank_300_gal_"),
    (4, "GBU_12"),
    (7, "GBU_12"),
    (8, "Fuel_tank_300_gal_"),
    (9, "LANTIRN_Targeting_Pod"),
    (10, "LAU_138_AIM_9M"),
)

_F14BU = _fit(
    "Heavy carrier strike",
    "2 GBU-31, 2 GBU-12, AIM-54C, 2 AIM-9M, 2 tanks and LANTIRN",
    (1, "LAU_138_AIM_9M"),
    (2, "AIM_54C_Mk47_"),
    (3, "Fuel_tank_300_gal_"),
    (4, "GBU_12"),
    (5, "GBU_31_V_2_B___JDAM__2000lb_GPS_Guided_Bomb_"),
    (6, "GBU_12"),
    (7, "GBU_31_V_2_B___JDAM__2000lb_GPS_Guided_Bomb_"),
    (8, "Fuel_tank_300_gal_"),
    (9, "LANTIRN_Targeting_Pod"),
    (10, "LAU_138_AIM_9M"),
)

_SU25 = _fit(
    "Battlefield interdiction",
    "4 laser-guided weapons, 2 cluster bombs, rockets and 2 R-60M",
    (1, "R_60M__AA_8_Aphid_B____IR_AAM"),
    (2, "B_8M1___20_x_UnGd_Rkts__80_mm_S_8KOM_HEAT_Frag"),
    (3, "RBK_500_255___30_x_PTAB_10_5__500kg_CBU_Heavy_HEAT_AP"),
    (4, "Kh_25ML__AS_10_Karen____300kg__ASM__Semi_Act_Laser__"),
    (5, "S_25L___320Kg__340mm_Laser_Guided_Rkt"),
    (6, "S_25L___320Kg__340mm_Laser_Guided_Rkt"),
    (7, "Kh_25ML__AS_10_Karen____300kg__ASM__Semi_Act_Laser__"),
    (8, "RBK_500_255___30_x_PTAB_10_5__500kg_CBU_Heavy_HEAT_AP"),
    (9, "B_8M1___20_x_UnGd_Rkts__80_mm_S_8KOM_HEAT_Frag"),
    (10, "R_60M__AA_8_Aphid_B____IR_AAM"),
)

_SU25T = _fit(
    "SEAD",
    "2 Kh-58U, 2 Kh-25MPU, 2 Kh-25ML, Fantasmagoria, ECM and 2 R-73",
    (1, "MPS_410"),
    (2, "R_73__AA_11_Archer____Infra_Red_"),
    (3, "Kh_25ML__AS_10_Karen____300kg__ASM__Semi_Act_Laser__"),
    (4, "Kh_25MPU__Updated_AS_12_Kegler____320kg__ARM__IN__Pas_Rdr__"),
    (5, "Kh_58U__AS_11_Kilter____640kg__ARM__IN__Pas_Rdr_"),
    (6, "L_081_Fantasmagoria_ELINT_pod"),
    (7, "Kh_58U__AS_11_Kilter____640kg__ARM__IN__Pas_Rdr_"),
    (8, "Kh_25MPU__Updated_AS_12_Kegler____320kg__ARM__IN__Pas_Rdr__"),
    (9, "Kh_25ML__AS_10_Karen____300kg__ASM__Semi_Act_Laser__"),
    (10, "R_73__AA_11_Archer____Infra_Red_"),
    (11, "MPS_410_"),
)

_APACHE = _fit(
    "Attack helicopter",
    "8 AGM-114L, 38 Hydra rockets, auxiliary tank and FCR",
    (1, "M261_MK151"),
    (2, "M299___4_x_AGM_114L_Hellfire"),
    (3, "M299___4_x_AGM_114L_Hellfire"),
    (4, "M261_MK151"),
    (5, "Internal_Auxiliary_Fuel_tank_100_gal_Combo_Pak"),
    (6, "AN_APG_78___Fire_Control_Radar_Radar_Frequency_Interferometer__FCR_RFI_"),
)

_HUEY = _fit(
    "Air assault",
    "door guns and 14 Hydra rockets",
    (1, "M134_L"),
    (2, "XM158_MK5"),
    (5, "XM158_MK5"),
    (6, "M134_R"),
)

_GAZELLE_M = _fit(
    "Anti-armour scout",
    "4 HOT-3 missiles and IR deflector",
    (1, "_2_x_HOT_3___ATGM__SACLOS__HEAT__"),
    (2, "_2_x_HOT_3___ATGM__SACLOS__HEAT"),
    (4, "IR_Deflector"),
)

_GAZELLE_L = _fit(
    "Armed scout",
    "GIAT cannon, 8 SNEB rockets, sand filter and IR deflector",
    (1, "GIAT_M621__240x_Combat_mix_4x_AP_1x_HE_"),
    (2, "Telson_8___8_x_UnGd_Rkts__68_mm_SNEB_Type_251_H1_HE"),
    (3, "Sand_Filter"),
    (4, "IR_Deflector"),
)


@dataclass
class _Scene:
    tactical: TacticalScene
    kutaisi: Airport
    senaki: Airport
    kobuleti: Airport
    sukhumi: Airport
    gudauta: Airport
    works: Point
    convoy_start: Point
    convoy_end: Point
    lz: Point
    sa10: Point
    sa11: Point
    tor: Point
    ewr: Point
    cap_south: Point
    cap_north: Point
    awacs_south: Point
    awacs_north: Point
    stennis: Point
    forrestal: Point


class CoastalLantern(MissionBuilder):
    """Fictional, coordination-tolerant public multiplayer mission."""

    name = "coastal_lantern"
    title = "Operation Coastal Lantern"
    difficulty = Difficulty.TRAINED
    terrain = Caucasus
    blue_task = (
        "Coastal Coalition: earn campaign success through any useful mix of CAP, "
        "SEAD, strike, CAS and helicopter assault tasks."
    )
    red_task = (
        "Northern Directorate: defend the coastal command works, road column and "
        "air-defence network."
    )
    start_time = datetime(2026, 8, 8, 9, 30, tzinfo=timezone.utc)
    weather = Weather(
        name="Summer coastal morning",
        season_temperature=24,
        clouds_base=2_100,
        clouds_thickness=500,
        clouds_density=4,
        visibility_distance=45_000,
        wind_at_ground=Wind(direction=250, speed=3),
        wind_at_2000=Wind(direction=260, speed=5),
        wind_at_8000=Wind(direction=275, speed=9),
    )

    def _assemble(self, m: Mission, plan: PlanOverlay) -> Assembled:
        scene = self._scene()
        usa, russia = m.country("USA"), m.country("Russia")
        self._claim_airfields(scene)

        stennis = self._carrier(
            m, usa, "CVN-74 John C. Stennis", ships.Stennis, scene.stennis, 74, 4, "STN"
        )
        forrestal = self._carrier(
            m, usa, "CV-59 Forrestal", ships.Forrestal, scene.forrestal, 59, 9, "FOR"
        )

        command, depot = self._targets(m, russia, scene)
        convoy = self._convoy(m, russia, scene)
        garrison = self._garrison(m, russia, scene)
        sa10, sa11, tor, ewr = self._air_defence(m, russia, scene)
        magic = self._support(m, usa, scene)
        self._sanctuaries(m, usa, russia, scene)
        self._iads(m, magic, sa10, sa11, tor, ewr)
        self._jtac(m, usa, scene, convoy)
        bandits = self._bandits(m, russia, scene)

        players, helos = self._players(m, usa, scene, stennis, forrestal)
        self._objectives(
            m, command, depot, convoy, garrison, sa10, bandits, helos, scene
        )
        threats = self._draw_plan(plan, scene)
        self._remarks(m)
        self._intro(m)
        return Assembled(scene.tactical.overlay, briefed_threats=threats)

    def _scene(self) -> _Scene:
        tactical = load_scene("caucasus")
        kutaisi = self._terrain.airports["Kutaisi"]
        senaki = self._terrain.airports["Senaki-Kolkhi"]
        kobuleti = self._terrain.airports["Kobuleti"]
        sukhumi = self._terrain.airports["Sukhumi-Babushara"]
        gudauta = self._terrain.airports["Gudauta"]
        works_anchor = self.at(42.714, 41.482)
        works = self._clear_ground(tactical, works_anchor, radius_m=2_500)
        convoy_start = convoy_spawn(
            tactical,
            self.at(42.622, 41.716),
            radius_m=8_000,
            avoid_built_up=False,
        )
        convoy_end = convoy_spawn(
            tactical,
            self.at(42.755, 41.542),
            radius_m=8_000,
            avoid_built_up=False,
        )
        lz = self._clear_ground(tactical, self.at(42.536, 41.817), radius_m=2_000)
        sa10 = self._clear_ground(tactical, self.at(42.790, 41.665), radius_m=4_000)
        sa11 = self._clear_ground(tactical, self.at(42.910, 41.455), radius_m=4_000)
        tor = self._clear_ground(
            tactical, offset(works, east_m=1_800, north_m=600), radius_m=1_000
        )
        ewr = self._clear_ground(tactical, self.at(43.055, 41.610), radius_m=5_000)
        return _Scene(
            tactical=tactical,
            kutaisi=kutaisi,
            senaki=senaki,
            kobuleti=kobuleti,
            sukhumi=sukhumi,
            gudauta=gudauta,
            works=works,
            convoy_start=convoy_start,
            convoy_end=convoy_end,
            lz=lz,
            sa10=sa10,
            sa11=sa11,
            tor=tor,
            ewr=ewr,
            cap_south=self.at(42.390, 41.350),
            cap_north=self.at(42.770, 41.250),
            awacs_south=self.at(41.930, 41.150),
            awacs_north=self.at(42.330, 40.980),
            stennis=self.at(42.050, 41.300),
            forrestal=self.at(42.520, 40.900),
        )

    def _clear_ground(
        self, tactical: TacticalScene, anchor: Point, *, radius_m: float
    ) -> Point:
        """Keep a surveyed dry anchor; search only when it is water or canopy."""
        if tactical.overlay.vegetation_at(anchor) not in NO_FOREST:
            return anchor
        return find_clear_spot(
            tactical.overlay, anchor, self._terrain, radius_m=radius_m
        )

    @staticmethod
    def _claim_airfields(scene: _Scene) -> None:
        for airport in (scene.kutaisi, scene.senaki, scene.kobuleti):
            airport.set_blue()
        for airport in (scene.sukhumi, scene.gudauta):
            airport.set_red()

    @staticmethod
    def _carrier(
        m: Mission,
        usa: Country,
        name: str,
        ship_type: type,
        position: Point,
        tacan: int,
        icls: int,
        callsign: str,
    ) -> ShipGroup:
        carrier = m.ship_group(usa, name, ship_type, position, heading=320)
        unit = carrier.units[0]
        carrier.points[0].tasks.extend(
            (
                task.ActivateBeaconCommand(tacan, "X", callsign, True, unit.id, False),
                task.ActivateICLSCommand(icls, unit.id),
                task.ActivateLink4Command(336, unit.id),
                task.ActivateACLSCommand(unit.id),
            )
        )
        carrier.add_waypoint(position.point_from_heading(320, 55_000), speed=46)
        escort = m.ship_group(
            usa,
            f"{name} Escort",
            ships.USS_Arleigh_Burke_IIa,
            position.point_from_heading(250, 7_000),
            heading=320,
        )
        escort.add_waypoint(escort.position.point_from_heading(320, 55_000), speed=46)
        return carrier

    def _targets(
        self, m: Mission, russia: Country, scene: _Scene
    ) -> tuple[StaticGroup, StaticGroup]:
        command = m.static_group(
            russia,
            "Lantern command bunker",
            statics.Fortification.Barracks_2,
            scene.works,
            heading=35,
        )
        depot = m.static_group(
            russia,
            "Lantern logistics hall",
            statics.Fortification.Workshop_A,
            offset(scene.works, east_m=520, north_m=180),
            heading=35,
        )
        return command, depot

    @staticmethod
    def _convoy(m: Mission, russia: Country, scene: _Scene) -> VehicleGroup:
        column = m.vehicle_group_platoon(
            russia,
            "Directorate road column",
            [
                vehicles.Armor.T_72B,
                vehicles.Armor.BMP_2,
                vehicles.Armor.BMP_2,
                vehicles.Unarmed.Ural_375,
                vehicles.Unarmed.Ural_375,
                vehicles.Unarmed.UAZ_469,
            ],
            scene.convoy_start,
            heading=int(scene.convoy_start.heading_between_point(scene.convoy_end)),
            formation=VehicleGroup.Formation.Line,
            move_formation=PointAction.OnRoad,
        )
        column.add_waypoint(
            scene.convoy_end, move_formation=PointAction.OnRoad, speed=38
        )
        set_skill(column, Skill.Average)
        return column

    @staticmethod
    def _garrison(m: Mission, russia: Country, scene: _Scene) -> VehicleGroup:
        group = m.vehicle_group_platoon(
            russia,
            "LZ Cedar garrison",
            [
                vehicles.Armor.BTR_80,
                vehicles.Armor.BTR_80,
                vehicles.Infantry.Paratrooper_AKS_74,
                vehicles.Infantry.Paratrooper_AKS_74,
                vehicles.Infantry.Paratrooper_RPG_16,
            ],
            offset(scene.lz, east_m=700, north_m=250),
            heading=220,
            formation=VehicleGroup.Formation.Scattered,
        )
        set_skill(group, Skill.Average)
        return group

    def _air_defence(
        self, m: Mission, russia: Country, scene: _Scene
    ) -> tuple[VehicleGroup, VehicleGroup, VehicleGroup, VehicleGroup]:
        sa10 = templates.VehicleTemplate.Russia.sa10_site(
            m, scene.sa10, 210, prefix="Lantern Grumble ", skill=Skill.High
        )
        sa10 = ad.disperse_site(
            sa10, radius_m=500, overlay=scene.tactical.overlay, terrain=self._terrain
        )
        sa11 = templates.VehicleTemplate.sa11_site(
            m, russia, scene.sa11, 210, prefix="Lantern Gadfly ", skill=Skill.High
        )
        sa11 = ad.disperse_site(
            sa11, radius_m=400, overlay=scene.tactical.overlay, terrain=self._terrain
        )
        tor = m.vehicle_group(
            russia,
            "Lantern Tor",
            vehicles.AirDefence.Tor_9A331,
            scene.tor,
            heading=220,
            group_size=2,
            formation=VehicleGroup.Formation.Scattered,
        )
        set_skill(tor, Skill.High)
        ewr = m.vehicle_group(
            russia,
            "Lantern EWR",
            vehicles.AirDefence.X_1L13_EWR,
            scene.ewr,
            heading=210,
        )
        set_skill(ewr, Skill.High)
        return sa10, sa11, tor, ewr

    @staticmethod
    def _support(m: Mission, usa: Country, scene: _Scene) -> FlyingGroup:
        magic = m.awacs_flight(
            usa,
            "Magic",
            planes.E_3A,
            airport=None,
            position=scene.awacs_south,
            race_distance=int(scene.awacs_south.distance_to_point(scene.awacs_north)),
            heading=int(scene.awacs_south.heading_between_point(scene.awacs_north)),
            altitude=8_500,
            speed=760,
            frequency=251,
        )
        m.refuel_flight(
            usa,
            "Texaco",
            planes.KC_135,
            airport=None,
            position=offset(scene.awacs_south, east_m=18_000, north_m=8_000),
            race_distance=55_000,
            heading=340,
            altitude=6_500,
            speed=720,
            frequency=252,
            tacanchannel="10X",
        )
        m.refuel_flight(
            usa,
            "Shell",
            planes.KC135MPRS,
            airport=None,
            position=offset(scene.awacs_south, east_m=-8_000, north_m=12_000),
            race_distance=55_000,
            heading=340,
            altitude=5_500,
            speed=680,
            frequency=253,
            tacanchannel="11X",
        )
        return magic

    @staticmethod
    def _sanctuaries(m: Mission, usa: Country, russia: Country, scene: _Scene) -> None:
        templates.VehicleTemplate.USA.hawk_site(
            m,
            offset(scene.kutaisi.position, east_m=-3_500, north_m=3_000),
            320,
            prefix="Kutaisi refuge ",
            skill=Skill.High,
        )
        ad.build_sa3_site(
            m,
            russia,
            offset(scene.gudauta.position, east_m=4_000, north_m=3_000),
            heading=210,
            launchers=4,
            prefix="Gudauta refuge ",
            overlay=scene.tactical.overlay,
            terrain=scene.gudauta.position._terrain,
        )

    def _iads(
        self,
        m: Mission,
        magic: FlyingGroup,
        sa10: VehicleGroup,
        sa11: VehicleGroup,
        tor: VehicleGroup,
        ewr: VehicleGroup,
    ) -> None:
        arm_iads(
            m,
            [
                Site(sa10, "SA-10 Grumble", go_live_percent=95),
                Site(sa11, "SA-11 Gadfly", go_live_percent=105),
                Site(tor, "SA-15 Gauntlet", go_live_percent=120),
                Site(ewr, "coastal EWR", role="ewr", act_as_ew=True),
            ],
            listeners=(Listener(magic, "Magic"),),
            voice=self._voice,
            coalition="blue",
            name="Lantern IADS",
            down_call="Magic: {label} has stopped radiating; treat it as dark, not destroyed.",
            up_call="Magic: {label} is radiating again.",
        )

    def _jtac(
        self, m: Mission, usa: Country, scene: _Scene, convoy: VehicleGroup
    ) -> None:
        pos = self._clear_ground(
            scene.tactical,
            offset(scene.convoy_start, east_m=-1_800, north_m=-900),
            radius_m=1_500,
        )
        warrior = m.vehicle_group_platoon(
            usa,
            "Warrior",
            [vehicles.Unarmed.Hummer, vehicles.Infantry.JTAC],
            pos,
            heading=int(pos.heading_between_point(scene.convoy_start)),
        )
        fac_attack_group(
            warrior,
            convoy,
            designation=task.Designation.Laser,
            frequency=_JTAC_FREQ,
            modulation=task.Modulation.AM,
            callsign=FacCallsign.WARRIOR,
        )
        jtac.arm_jtac_coords(
            m,
            (
                jtac.CoordTarget(
                    convoy,
                    "Warrior 1-1",
                    "Directorate road column",
                    laser_code=_LASER_CODE,
                ),
            ),
            menu_title="Warrior 1-1",
            push_at_s=180,
        )

    def _bandits(
        self, m: Mission, russia: Country, scene: _Scene
    ) -> tuple[FlyingGroup, FlyingGroup]:
        zone = m.triggers.add_triggerzone(
            scene.works, radius=75_000, hidden=True, name="Lantern GCI zone"
        )
        migs = m.intercept_flight(
            russia,
            "Directorate Fulcrum",
            planes.MiG_29S,
            scene.gudauta,
            zone,
            late_activation=True,
            start_type=StartType.Cold,
            speed=900,
            altitude=8_000,
            max_engage_distance=95_000,
            group_size=4,
        )
        flankers = m.intercept_flight(
            russia,
            "Directorate Flanker",
            planes.Su_27,
            scene.sukhumi,
            zone,
            late_activation=True,
            start_type=StartType.Cold,
            speed=920,
            altitude=9_000,
            max_engage_distance=105_000,
            group_size=4,
        )
        set_skill(migs, Skill.High)
        set_skill(flankers, Skill.Average)
        apply_ai_difficulty(migs, self.difficulty)
        apply_ai_difficulty(flankers, self.difficulty)
        return migs, flankers

    def _players(
        self,
        m: Mission,
        usa: Country,
        scene: _Scene,
        stennis: ShipGroup,
        forrestal: ShipGroup,
    ) -> tuple[list[FlyingGroup], list[FlyingGroup]]:
        all_groups: list[FlyingGroup] = []
        helo_groups: list[FlyingGroup] = []

        land = (
            ("Viper", planes.F_16C_50, scene.kutaisi, task.SEAD, _F16, "sead", 760),
            (
                "Strike Eagle",
                planes.F_15ESE,
                scene.kutaisi,
                task.PinpointStrike,
                _F15E,
                "strike",
                760,
            ),
            ("Hawg", planes.A_10C_2, scene.kutaisi, task.CAS, _A10, "cas", 470),
            ("Eagle", planes.F_15C, scene.senaki, task.CAP, _F15C, "cap", 820),
            ("Frogfoot", planes.Su_25, scene.senaki, task.CAS, _SU25, "cas", 600),
            ("Toad", planes.Su_25T, scene.senaki, task.SEAD, _SU25T, "sead", 600),
        )
        for name, aircraft, airport, role, fits, route, speed in land:
            sections = player_flight(
                m,
                country=usa,
                name=name,
                aircraft_type=aircraft,
                airport=airport,
                maintask=role,
                start_type=StartType.Warm,
                section_start_types=_STARTS,
                slots=_SLOTS,
                loadouts=fits,
            )
            for section in sections:
                if laser.laser_guided_stores(section):
                    laser.set_code(section, _LASER_CODE)
            self._route_land(sections, airport, scene, route, speed)
            all_groups.extend(sections)

        carrier_roster = (
            (
                "Hornet",
                planes.FA_18C_hornet,
                stennis,
                task.PinpointStrike,
                _HORNET,
                "strike",
                740,
            ),
            (
                "Tomcat Bravo Uniform",
                planes.F_14BU,
                stennis,
                task.PinpointStrike,
                _F14BU,
                "strike",
                780,
            ),
            (
                "Tomcat Alpha",
                planes.F_14A_135_GR,
                forrestal,
                task.CAP,
                _F14A,
                "cap",
                820,
            ),
            (
                "Tomcat Bravo",
                planes.F_14B,
                forrestal,
                task.PinpointStrike,
                _F14B,
                "strike",
                780,
            ),
        )
        for name, aircraft, carrier, role, fits, route, speed in carrier_roster:
            sections = player_flight_from_unit(
                m,
                country=usa,
                name=name,
                aircraft_type=aircraft,
                pad_group=carrier,
                maintask=role,
                start_type=StartType.Warm,
                section_start_types=_STARTS,
                slots=_SLOTS,
                loadouts=fits,
            )
            for section in sections:
                if laser.laser_guided_stores(section):
                    laser.set_code(section, _LASER_CODE)
            self._route_carrier(sections, carrier, scene, route, speed)
            all_groups.extend(sections)

        helos = (
            ("Apache", helicopters.AH_64D_BLK_II, scene.senaki, task.CAS, _APACHE, 250),
            ("Huey", helicopters.UH_1H, scene.kobuleti, task.Transport, _HUEY, 190),
            (
                "Gazelle HOT",
                helicopters.SA342M,
                scene.kobuleti,
                task.CAS,
                _GAZELLE_M,
                210,
            ),
            (
                "Gazelle Lima",
                helicopters.SA342L,
                scene.senaki,
                task.CAS,
                _GAZELLE_L,
                210,
            ),
        )
        for name, aircraft, airport, role, fits, speed in helos:
            sections = player_flight(
                m,
                country=usa,
                name=name,
                aircraft_type=aircraft,
                airport=airport,
                maintask=role,
                start_type=StartType.Warm,
                section_start_types=_STARTS,
                slots=_SLOTS,
                loadouts=fits,
            )
            self._route_helo(sections, airport, scene, speed)
            all_groups.extend(sections)
            helo_groups.extend(sections)
        return all_groups, helo_groups

    @staticmethod
    def _route_land(
        sections: Sequence[FlyingGroup],
        airport: Airport,
        scene: _Scene,
        role: str,
        speed: int,
    ) -> None:
        for flight in sections:
            flight.add_runway_waypoint(airport)
            if role == "cap":
                flight.add_waypoint(scene.cap_south, 7_500, speed, "CAP SOUTH")
                flight.add_waypoint(scene.cap_north, 7_500, speed, "CAP NORTH")
            elif role == "sead":
                flight.add_waypoint(
                    offset(scene.works, east_m=-22_000, north_m=-22_000),
                    5_500,
                    speed,
                    "SEAD PUSH",
                )
                flight.add_waypoint(scene.sa10, 4_500, speed, "SA-10 AREA")
                flight.add_waypoint(scene.sa11, 4_500, speed, "SA-11 AREA")
            elif role == "strike":
                flight.add_waypoint(
                    offset(scene.works, east_m=-18_000, north_m=-16_000),
                    5_000,
                    speed,
                    "STRIKE IP",
                )
                flight.add_waypoint(scene.works, 4_000, speed, "COMMAND BUNKER")
                flight.add_waypoint(
                    offset(scene.works, east_m=520, north_m=180),
                    4_000,
                    speed,
                    "LOGISTICS HALL",
                )
            else:
                flight.add_waypoint(scene.convoy_start, 2_500, speed, "CAS SOUTH")
                flight.add_waypoint(scene.convoy_end, 2_500, speed, "CAS NORTH")
            flight.add_runway_waypoint(airport)
            flight.land_at(airport)

    @staticmethod
    def _route_carrier(
        sections: Sequence[FlyingGroup],
        carrier: ShipGroup,
        scene: _Scene,
        role: str,
        speed: int,
    ) -> None:
        for flight in sections:
            if role == "cap":
                flight.add_waypoint(scene.cap_south, 7_500, speed, "CAP SOUTH")
                flight.add_waypoint(scene.cap_north, 7_500, speed, "CAP NORTH")
            else:
                flight.add_waypoint(
                    offset(scene.works, east_m=-20_000, north_m=-18_000),
                    5_000,
                    speed,
                    "STRIKE IP",
                )
                flight.add_waypoint(scene.works, 4_000, speed, "COMMAND BUNKER")
                flight.add_waypoint(
                    offset(scene.works, east_m=520, north_m=180),
                    4_000,
                    speed,
                    "LOGISTICS HALL",
                )
            flight.add_waypoint(carrier.position, 1_200, 600, "CARRIER MARSHAL")

    @staticmethod
    def _route_helo(
        sections: Sequence[FlyingGroup], airport: Airport, scene: _Scene, speed: int
    ) -> None:
        for flight in sections:
            flight.add_runway_waypoint(airport)
            flight.add_waypoint(scene.convoy_start, 250, speed, "ROAD COLUMN")
            flight.add_waypoint(scene.lz, 120, speed, "LZ CEDAR")
            flight.add_waypoint(scene.convoy_start, 250, speed, "EGRESS SOUTH")
            flight.add_runway_waypoint(airport)
            flight.land_at(airport)

    def _objectives(
        self,
        m: Mission,
        command: StaticGroup,
        depot: StaticGroup,
        convoy: VehicleGroup,
        garrison: VehicleGroup,
        sa10: VehicleGroup,
        bandits: Sequence[FlyingGroup],
        helos: Sequence[FlyingGroup],
        scene: _Scene,
    ) -> None:
        self._score(
            m,
            "Command node destroyed",
            (condition.UnitDead(command.units[0].id),),
            2,
            "Magic: the Directorate command node is destroyed. Two campaign points secured.",
        )
        self._score(
            m,
            "Logistics hall destroyed",
            (condition.UnitDead(depot.units[0].id),),
            1,
            "Magic: the coastal logistics hall is down. One campaign point secured.",
        )
        self._score(
            m,
            "Road column defeated",
            (condition.GroupLifeLess(convoy.id, 30),),
            2,
            "Warrior: the road column is combat ineffective. Two campaign points secured.",
        )
        self._score(
            m,
            "SA-10 defeated",
            (condition.GroupLifeLess(sa10.id, 35),),
            1,
            "Magic: the SA-10 battalion is combat ineffective. One campaign point secured.",
        )
        self._score(
            m,
            "CAP task complete",
            tuple(condition.GroupDead(group.id) for group in bandits),
            2,
            "Magic: Directorate fighter strength over the coast is broken. Two campaign points secured.",
        )
        lz_zone = m.triggers.add_triggerzone(
            scene.lz, radius=900, hidden=False, name="LZ CEDAR"
        )
        # Coalition-in-zone with the HELICOPTER filter includes every supported
        # module without an OR chain over eight separate DCS groups.
        self._score(
            m,
            "LZ Cedar secured",
            (
                condition.GroupDead(garrison.id),
                condition.PartOfCoalitionInZone("blue", lz_zone.id, "HELICOPTER"),
            ),
            2,
            "Magic: Coalition helicopters are on LZ Cedar and the garrison is clear. Two campaign points secured.",
        )
        success = mission_triggers.message_to_coalition(
            m,
            comment="Campaign success",
            conditions=(condition.FlagIsMore(_SCORE_FLAG, _SUCCESS_SCORE - 1),),
            voice=self._voice,
            text=(
                "Magic: Coastal Lantern is a success. The Directorate position is no longer tenable. "
                "Finish any attacks already in progress, then recover."
            ),
            seconds=30,
        )
        success.add_action(action.SetFlagValue(901, 1))

    def _score(
        self,
        m: Mission,
        comment: str,
        conditions: Sequence[condition.Condition],
        points: int,
        text: str,
    ) -> None:
        rule = mission_triggers.message_to_coalition(
            m,
            comment=comment,
            conditions=conditions,
            voice=self._voice,
            text=text,
            seconds=20,
        )
        rule.add_action(
            InlineDoScript(
                f"trigger.action.setUserFlag({_SCORE_FLAG}, "
                f"trigger.misc.getUserFlag({_SCORE_FLAG}) + {points})"
            )
        )

    def _draw_plan(self, plan: PlanOverlay, scene: _Scene):
        plan.objective(scene.works, "STRIKE — COMMAND WORKS", radius=4_000)
        plan.objective(scene.convoy_start, "CAS — ROAD COLUMN", radius=5_000)
        plan.objective(scene.lz, "HELO — LZ CEDAR", radius=2_000)
        plan.route((scene.convoy_start, scene.convoy_end), "DIRECTORATE ROAD COLUMN")
        plan.orbit(scene.cap_south, scene.cap_north, "COALITION CAP")
        plan.orbit(scene.awacs_south, scene.awacs_north, "MAGIC 251.000")
        plan.waypoint_label(scene.stennis, "STENNIS — TACAN 74X / ICLS 4")
        plan.waypoint_label(scene.forrestal, "FORRESTAL — TACAN 59X / ICLS 9")
        return [
            *dtc.briefed(
                plan.threat(
                    scene.sa10,
                    radius=75_000,
                    label="SA-10",
                    icon=StandardIcon.AirDefense,
                ),
                dtc.SA_10,
                label="SA-10 Grumble",
            ),
            *dtc.briefed(
                plan.threat(
                    scene.sa11,
                    radius=42_000,
                    label="SA-11",
                    icon=StandardIcon.AirDefense,
                ),
                dtc.SA_11,
                label="SA-11 Gadfly",
            ),
            *dtc.briefed(
                plan.threat(
                    scene.tor,
                    radius=12_000,
                    label="SA-15",
                    icon=StandardIcon.AirDefense,
                ),
                dtc.SA_15,
                label="SA-15 Gauntlet",
            ),
        ]

    @staticmethod
    def _remarks(m: Mission) -> None:
        kneeboard.remark(
            m, "Every module: 8 slots — first section HOT, second section COLD."
        )
        kneeboard.remark(m, "Stennis: TACAN 74X, ICLS 4. Forrestal: TACAN 59X, ICLS 9.")
        kneeboard.remark(
            m,
            "Magic 251.000 AM. Texaco 252.000 / 10X boom. Shell 253.000 / 11X basket.",
        )
        kneeboard.remark(
            m,
            f"Warrior 1-1: {_JTAC_FREQ}.000 AM, laser {_LASER_CODE}; live coordinates in F10 Other.",
        )
        kneeboard.remark(
            m, "Campaign success requires 7 points; all taskings are independent."
        )

    def _intro(self, m: Mission) -> None:
        mission_triggers.intro(
            m,
            comment="Operation Coastal Lantern opening picture",
            voice=self._voice,
            text=(
                "Magic: Coastal Lantern is active. Fighter, SEAD, strike, CAS and helicopter taskings "
                "are independent. The coastal IADS is networked and may shut down when threatened. "
                "Choose the work your package can do; seven campaign points will break the position."
            ),
        )

    def _in_game_briefing(self) -> str:
        return f"""OPERATION COASTAL LANTERN

SITUATION
The fictional Northern Directorate holds the coast north of the Enguri and has converted an old works near Ochamchira into a command and logistics hub. Its SA-10, SA-11, SA-15 and early-warning radar are linked as an integrated network: emitters may remain silent, share tracks and shut down against anti-radiation fire.

MISSION
The Coastal Coalition must earn {_SUCCESS_SCORE} campaign points. Every task is independent; coordination helps but no package must wait for another.

TASKS
CAP: destroy both Directorate fighter groups (2 points).
STRIKE: destroy the command bunker (2) and logistics hall (1).
SEAD: render the SA-10 battalion combat ineffective (1).
CAS: render the moving road column combat ineffective (2).
HELO: clear the LZ Cedar garrison and put any coalition helicopter inside the marked LZ (2).

THREATS
Long-range SA-10 and SA-11 cover the coast. SA-15 protects the works. The rings on F10 are trained-intelligence estimates, not exact emitter coordinates. Expect four MiG-29S and four Su-27 to scramble from cold alert once coalition aircraft enter the coastal GCI zone.

SUPPORT
Magic 251.000 AM. Texaco boom 252.000 AM / 10X. Shell basket 253.000 AM / 11X. Warrior 1-1 {_JTAC_FREQ}.000 AM, laser {_LASER_CODE}; request current column coordinates through F10 Other.

CARRIER RECOVERY
Stennis: TACAN 74X, ICLS 4. Forrestal: TACAN 59X, ICLS 9.

STARTS
Every module has eight seats at one location: four hot in the lead section and four cold in section 2. Hornets and F-14B(U) operate from Stennis; F-14A and F-14B operate from Forrestal.
"""

    def readme(self) -> str:
        return f"""# {self.title}

## Scenario

The fictional **Northern Directorate** holds the coast north of the Enguri. The
**Coastal Coalition** is attacking its command network near Ochamchira. This is
a wide public multiplayer mission: CAP, SEAD, strike, CAS and helicopter groups
can all contribute without waiting for another package to complete first.

Campaign success requires **{_SUCCESS_SCORE} points**:

| Task | Requirement | Points |
|---|---|---:|
| CAP | Destroy both four-ship Directorate fighter groups | 2 |
| Strike | Destroy the command bunker | 2 |
| Strike | Destroy the logistics hall | 1 |
| SEAD | Reduce the SA-10 battalion below combat effectiveness | 1 |
| CAS | Reduce the road column below combat effectiveness | 2 |
| Helicopters | Clear LZ Cedar and put a coalition helicopter in the LZ | 2 |

The total available is ten points, so a missing specialty or an uncoordinated
package does not deadlock the event.

## Client roster

Every module has **8 slots at one operating location**, divided into a four-seat
hot section and a four-seat cold section.

| Location | Module | Flight | Primary role |
|---|---|---|---|
| Kutaisi | F-16C-50 | Viper / Viper 2 | SEAD |
| Kutaisi | F-15E Strike Eagle | Strike Eagle / Strike Eagle 2 | Heavy strike |
| Kutaisi | A-10C II | Hawg / Hawg 2 | CAS |
| Senaki-Kolkhi | F-15C | Eagle / Eagle 2 | CAP |
| Senaki-Kolkhi | Su-25 | Frogfoot / Frogfoot 2 | CAS/interdiction |
| Senaki-Kolkhi | Su-25T | Toad / Toad 2 | SEAD |
| CVN-74 Stennis | F/A-18C | Hornet / Hornet 2 | Precision strike |
| CVN-74 Stennis | F-14B(U) | Tomcat Bravo Uniform / section 2 | Heavy strike |
| CV-59 Forrestal | F-14A | Tomcat Alpha / section 2 | Fleet CAP |
| CV-59 Forrestal | F-14B | Tomcat Bravo / section 2 | Carrier strike |
| Senaki-Kolkhi | AH-64D | Apache / Apache 2 | Attack helicopter |
| Kobuleti | UH-1H | Huey / Huey 2 | Air assault |
| Kobuleti | SA342M Gazelle | Gazelle HOT / section 2 | Anti-armour scout |
| Senaki-Kolkhi | SA342L Gazelle | Gazelle Lima / section 2 | Armed scout |

Total capacity is **112 client slots**. The mission is intentionally permissive:
players may take a different role from the route suggested for their module.

## Threat picture

The SA-10, SA-11, SA-15 and EWR use the mission creator's vendored Skynet-IADS
integration. Sites share detections, delay emissions and may shut down against
observed anti-radiation launches. A dark emitter is not necessarily dead.

Four MiG-29S and four Su-27 start cold at Directorate fields and scramble when
coalition aircraft enter the coastal GCI zone. Magic is airborne throughout.

## Support and recovery

| Asset | Frequency / channel |
|---|---|
| Magic E-3A | 251.000 AM |
| Texaco KC-135 (boom) | 252.000 AM, TACAN 10X |
| Shell KC-135MPRS (basket) | 253.000 AM, TACAN 11X |
| Warrior 1-1 JTAC | {_JTAC_FREQ}.000 AM, laser {_LASER_CODE} |
| CVN-74 Stennis | TACAN 74X, ICLS 4 |
| CV-59 Forrestal | TACAN 59X, ICLS 9 |

Warrior's moving-target coordinates are available under **F10 Other** and are
formatted for the requesting cockpit. All essential routes, estimated threat
rings, task areas and carrier recovery data are also on the F10 plan and
kneeboard.

## Regenerate

```bash
uv run dcs-mission-creator generate {self.name} --output-dir out/{self.name}
```
"""


def main() -> None:
    run_cli(CoastalLantern)


if __name__ == "__main__":
    main()
