"""Caucasus 'Batumi TACAN Trainer' — a short, weather-limited nav sortie.

Choose an A-10C, F-16C-50, or F/A-18C from the blue client slots at Batumi.
The whole exercise is one short leg north along the coast to Kobuleti, the
nearest other Caucasus airfield with a TACAN: KBL, channel 67X.  There is no
opposition and no time pressure; the weather is the training value.  Low cloud
removes the easy visual reference and the 10 kt crosswind at Kobuleti makes the
arrival a deliberate landing rather than a sightseeing flight.
"""

from __future__ import annotations

from datetime import datetime, timezone

from dcs import planes, task
from dcs.mission import Mission, StartType
from dcs.terrain.caucasus.caucasus import Caucasus
from dcs.terrain.terrain import Airport
from dcs.unitgroup import FlyingGroup

from dcs_mission_creator.core.cli import run_cli
from dcs_mission_creator.core.difficulty import Difficulty
from dcs_mission_creator.core.loadout import Loadout
from dcs_mission_creator.core.map_draw import PlanOverlay
from dcs_mission_creator.core.mission_builder import Assembled, MissionBuilder
from dcs_mission_creator.core.mission_kit import player_flight
from dcs_mission_creator.core.placement import load_scene
from dcs_mission_creator.core.weather import Weather, Wind

_KOBULETI_TACAN = "67X"
_CRUISE_ALTITUDE_M = 1_500
_TRAINING_FITS = (
    Loadout(
        role="Navigation lead",
        carries="clean training configuration",
        stores=(),
    ),
    Loadout(
        role="Navigation wing",
        carries="clean training configuration",
        stores=(),
    ),
)


class BatumiTacanTrainer(MissionBuilder):
    """A selectable-module, Batumi-to-Kobuleti TACAN navigation exercise."""

    name = "batumi_tacan_trainer"
    title = "Batumi TACAN Trainer"
    difficulty = Difficulty.RECRUIT
    terrain = Caucasus
    blue_task = "Navigate from Batumi to Kobuleti using KBL TACAN 67X; land safely."
    red_task = "No tasking: this is a blue navigation and landing exercise."
    # DCS reads this as map-local time; the UTC marker is only an explicit record.
    start_time = datetime(2026, 10, 15, 9, 0, tzinfo=timezone.utc)
    # Kobuleti's active runway is roughly 250°. Wind from 160° is therefore a
    # crosswind, and 5 m/s is 9.7 kt — the requested 10 kt in DCS's integer API.
    weather = Weather(
        name="Low cloud, Kobuleti crosswind",
        season_temperature=16,
        clouds_base=500,
        clouds_thickness=450,
        clouds_density=8,
        visibility_distance=8_000,
        wind_at_ground=Wind(direction=160, speed=5),
        wind_at_2000=Wind(direction=160, speed=5),
        wind_at_8000=Wind(direction=170, speed=8),
    )

    def _assemble(self, m: Mission, plan: PlanOverlay) -> Assembled:
        """Claim the two fields, add each selectable module, and draw one route."""
        batumi, kobuleti = self._setup_airports()
        usa = m.country("USA")
        scene = load_scene("caucasus")

        for name, aircraft, speed in (
            ("Hawg", planes.A_10C, 430),
            ("Viper", planes.F_16C_50, 700),
            ("Hornet", planes.FA_18C_hornet, 650),
        ):
            for flight in player_flight(
                m,
                country=usa,
                name=name,
                aircraft_type=aircraft,
                airport=batumi,
                maintask=task.CAP,
                start_type=StartType.Warm,
                slots=self.players,
                # Clear pylons make the selectable modules equally available
                # without inventing aircraft-specific combat fits.
                loadouts=_TRAINING_FITS,
            ):
                self._route(flight, batumi, kobuleti, speed)

        plan.route((batumi.position, kobuleti.position), label="BATUMI → KOBULETI")
        plan.waypoint_label(kobuleti.position, f"KBL TACAN {_KOBULETI_TACAN}")
        return Assembled(scene.overlay)

    def _setup_airports(self) -> tuple[Airport, Airport]:
        """Make Batumi and the TACAN-equipped destination blue-owned."""
        batumi = self._terrain.airports["Batumi"]
        kobuleti = self._terrain.airports["Kobuleti"]
        batumi.set_blue()
        kobuleti.set_blue()
        return batumi, kobuleti

    @staticmethod
    def _route(
        flight: FlyingGroup, departure: Airport, destination: Airport, speed: int
    ) -> None:
        """Fly the short coastal leg, then land at the TACAN destination."""
        flight.add_runway_waypoint(departure)
        flight.add_waypoint(
            destination.position,
            altitude=_CRUISE_ALTITUDE_M,
            speed=speed,
            name=f"KBL TACAN {_KOBULETI_TACAN}",
        )
        flight.land_at(destination)

    def _in_game_briefing(self) -> str:
        return (
            "BATUMI TACAN TRAINER\n\n"
            "Select Hawg (A-10C), Viper (F-16C-50), or Hornet (F/A-18C) at "
            "Batumi. Navigate north along the coast to Kobuleti using KBL TACAN "
            f"{_KOBULETI_TACAN}, then land.\n\n"
            "Weather: low cloud base 500 m, 8 km visibility. Kobuleti has a "
            "10 kt crosswind for the landing. No threats or time pressure."
        )

    def readme(self) -> str:
        return f"""# {self.title}

## Mission

Start at **Batumi** and land at **Kobuleti**, the nearest other airfield with a
TACAN. Select one of the blue client flights in the slot list:

| Flight | Module | Role |
|---|---|---|
| Hawg | A-10C | Navigation trainer |
| Viper | F-16C-50 | Navigation trainer |
| Hornet | F/A-18C | Navigation trainer |

Each aircraft type has {self.players} selectable client slot(s). The aircraft
are clean; this mission is about instrument navigation and landing technique.

## Navigation

| Item | Value |
|---|---|
| Departure | Batumi |
| Destination | Kobuleti |
| TACAN | **KBL {_KOBULETI_TACAN}** |
| Route | Follow the coast north from Batumi to Kobuleti |

## Weather

Low cloud is based at 500 m with 8 km visibility. At Kobuleti, wind is from
160° at 5 m/s (approximately **10 kt**), producing a crosswind for the active
runway. There are no threats and no time limit.

## Re-generate

```bash
uv run dcs-mission-creator generate {self.name} --output-dir out/{self.name}
```
"""


def main() -> None:
    run_cli(BatumiTacanTrainer)


if __name__ == "__main__":
    main()
