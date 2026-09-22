# Project instructions

Read [CLAUDE.md](CLAUDE.md) before creating or modifying a mission. It is the
authoritative guide to this project's mission design, generation workflow, and
quality conventions.

## Mission work

- Add mission modules under `src/dcs_mission_creator/missions/`.
- Implement each mission as a `MissionBuilder` subclass, following the
  `_assemble`, in-game briefing, and README conventions in `CLAUDE.md`.
- Use `PlanOverlay` for F10 plan drawings and map-overlay helpers for
  terrain-dependent placement and routing; do not hand-place such positions.
- Keep player-count, difficulty, briefing, map drawing, and DTC information
  consistent with the conventions documented in `CLAUDE.md`.

## Verification

- Run the relevant tests and generate the affected mission before handing off
  changes when the required map overlay and dependencies are available.
- Generate a mission explicitly to a workspace output directory, for example:
  `uv run dcs-mission-creator generate <slug> --output-dir out/<slug>`.
