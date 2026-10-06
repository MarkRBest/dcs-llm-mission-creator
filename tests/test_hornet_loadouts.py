"""The optional Hornet fits use stores on stations the Hornet actually has."""

from __future__ import annotations

import pytest
from dcs import planes

from dcs_mission_creator.core import hornet_loadouts, loadout
from dcs_mission_creator.core.player_aircraft import PlayerAircraft


@pytest.mark.parametrize(
    "fits",
    [
        hornet_loadouts.sead_jsow(),
        hornet_loadouts.cluster_and_laser(),
        hornet_loadouts.laser_and_cap(),
        hornet_loadouts.jdam_and_laser(),
        hornet_loadouts.sead_and_cap(),
        hornet_loadouts.penetrator_and_cap(),
        hornet_loadouts.cap(),
    ],
)
def test_hornet_fits_use_declared_pylons(fits) -> None:
    """Catch a Viper station/store name leaking into an F/A-18C fit."""
    for fit in fits:
        for station, store in fit.stores:
            assert loadout.pylon_entry(planes.FA_18C_hornet, station, store), (
                f"{fit.role}: {store} is not available on Hornet station {station}"
            )


def test_f16_mission_switches_its_client_type_and_fits() -> None:
    """The choice changes both the airframe and stores, never just one."""
    from dcs_mission_creator.missions.caucasus.coastal_cover import (
        _FITS,
        _HORNET_FITS,
        CoastalCover,
    )

    hornet = CoastalCover(aircraft=PlayerAircraft.FA_18C)
    assert hornet.player_aircraft_type() is planes.FA_18C_hornet
    assert hornet.player_loadouts(_FITS, _HORNET_FITS) == _HORNET_FITS
