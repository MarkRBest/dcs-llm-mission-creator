"""Role-specific F/A-18C fits for missions that can also fly the Hornet.

The Viper's stations and payload split are intentionally not translated
mechanically.  These fits use the Hornet's actual stations: AIM-9X on 1/9,
dual AMRAAM rails on 2/8, ATFLIR on 4, and the 330-gallon centre tank on 5.
The mission selects a fit whose weapons answer its objective.
"""

from __future__ import annotations

from dcs_mission_creator.core.loadout import Loadout

_AIM9 = "AIM_9X_Sidewinder_IR_AAM"
_AIM120_RACK = "LAU_115_2_LAU_127_AIM_120C"
_ATFLIR = "AN_ASQ_228_ATFLIR___Targeting_Pod"
_TANK = "FPU_8A_Fuel_Tank_330_gallons"
_HARM = "AGM_88C_HARM___High_Speed_Anti_Radiation_Missile_"
_JSOW_RACK = "BRU_55_with_2_x_AGM_154A___JSOW_CEB__CBU_type_"
_GBU12_RACK = "BRU_33_with_2_x_GBU_12___500lb_Laser_Guided_Bomb"
_GBU38_RACK = "BRU_55_with_2_x_GBU_38___JDAM__500lb_GPS_Guided_Bomb"
_GBU31_PEN = "GBU_31_V_3_B___JDAM__2000lb_GPS_Guided_Penetrator_Bomb"


def _defence(*stores: tuple[int, str]) -> tuple[tuple[int, str], ...]:
    """Add the common Hornet self-defence, pod, and fuel stations."""
    return (
        (1, _AIM9),
        (2, _AIM120_RACK),
        *stores,
        (4, _ATFLIR),
        (5, _TANK),
        (8, _AIM120_RACK),
        (9, _AIM9),
    )


def sead_jsow() -> tuple[Loadout, Loadout]:
    """Suppress emitters, then destroy the site with standoff cluster JSOWs."""
    return (
        Loadout(
            "HARM",
            "two AGM-88C HARM, four AIM-120C, two AIM-9X, ATFLIR, 330 gal",
            _defence((3, _HARM), (7, _HARM)),
        ),
        Loadout(
            "JSOW-A*4",
            "four AGM-154A cluster JSOW, four AIM-120C, two AIM-9X, ATFLIR, 330 gal",
            _defence((3, _JSOW_RACK), (7, _JSOW_RACK)),
        ),
    )


def cluster_and_laser() -> tuple[Loadout, Loadout]:
    """Use cluster JSOWs for dispersed vehicles and laser bombs for armour."""
    return (
        Loadout(
            "JSOW-A*4",
            "four AGM-154A cluster JSOW, four AIM-120C, two AIM-9X, ATFLIR, 330 gal",
            _defence((3, _JSOW_RACK), (7, _JSOW_RACK)),
        ),
        Loadout(
            "GBU-12*4",
            "four GBU-12 laser-guided bombs, four AIM-120C, two AIM-9X, ATFLIR, 330 gal",
            _defence((3, _GBU12_RACK), (7, _GBU12_RACK)),
        ),
    )


def laser_and_cap() -> tuple[Loadout, Loadout]:
    """Attack a point target with laser bombs while the wingman covers it."""
    return (
        Loadout(
            "GBU-12*2",
            "two GBU-12 laser-guided bombs, four AIM-120C, two AIM-9X, ATFLIR, 330 gal",
            _defence((3, _GBU12_RACK)),
        ),
        Loadout("CAP", "four AIM-120C, two AIM-9X, ATFLIR, 330 gal", _defence()),
    )


def jdam_and_laser() -> tuple[Loadout, Loadout]:
    """Combine satellite-aided and laser-guided attacks in one strike fit."""
    return (
        Loadout(
            "JDAM+LGB",
            "two GBU-38 JDAM and two GBU-12 laser-guided bombs, four AIM-120C, two AIM-9X, ATFLIR, 330 gal",
            _defence((3, _GBU38_RACK), (7, _GBU12_RACK)),
        ),
        Loadout("CAP", "four AIM-120C, two AIM-9X, ATFLIR, 330 gal", _defence()),
    )


def sead_and_cap() -> tuple[Loadout, Loadout]:
    """Suppress a radar while the second Hornet keeps an air-to-air reserve."""
    return (
        Loadout(
            "HARM",
            "two AGM-88C HARM, four AIM-120C, two AIM-9X, ATFLIR, 330 gal",
            _defence((3, _HARM), (7, _HARM)),
        ),
        Loadout("CAP", "four AIM-120C, two AIM-9X, ATFLIR, 330 gal", _defence()),
    )


def penetrator_and_cap() -> tuple[Loadout, Loadout]:
    """Carry penetrator JDAMs for hardened targets and a dedicated escort."""
    return (
        Loadout(
            "GBU-31(V)3/B",
            "two GBU-31(V)3/B 2,000 lb penetrator JDAM, four AIM-120C, two AIM-9X, ATFLIR, 330 gal",
            _defence((3, _GBU31_PEN), (7, _GBU31_PEN)),
        ),
        Loadout("CAP", "four AIM-120C, two AIM-9X, ATFLIR, 330 gal", _defence()),
    )


def cap() -> tuple[Loadout, Loadout]:
    """A six-missile Hornet sweep pair with range for the on-station fight."""
    fit = Loadout(
        "A/A",
        "four AIM-120C, two AIM-9X, ATFLIR, 330 gal",
        _defence(),
    )
    return (fit, fit)
