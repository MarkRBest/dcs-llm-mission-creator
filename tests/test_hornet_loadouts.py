"""Hornet client fits use stores on stations the module actually has."""

from __future__ import annotations

import pytest
from dcs import planes

from dcs_mission_creator.core import hornet_loadouts, loadout


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
