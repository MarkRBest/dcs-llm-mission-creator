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

## Known mission pitfalls

- The fighter scramble in `afghanistan/bagram_convoy_ambush.py` has repeatedly
  failed to get the fighters to leave Kabul; previous patches did not fix it.
  Treat this as unresolved. Do not count group activation or a fired trigger as
  proof of a scramble: verify in DCS that the AI taxis, takes off, and follows
  its route away from Kabul. Compare the actual trigger and route sequence with
  `bagram_wildcard.py` before reusing either pattern.
- In the convoy-ambush testing, MANPADS appeared as part of the fighter-launch
  sequence, but the reason for that coupling was not established. Treat it as
  an observed trigger-order/condition symptom, not evidence that the MANPADS
  and fighter scramble use the same successful launch mechanism; inspect and
  test their activation conditions separately.
- Validate every radio frequency against the exact field, unit radio, and DCS
  serialization convention. This project uses MHz for ordinary group radio
  frequencies, while some task parameters (such as FAC task frequencies) use
  Hz; do not copy a value between fields without checking its units and
  serializer. A Huey set to 127 MHz was observed to make a mission fail to
  load, so check the aircraft's supported radio band and the generated mission
  data, then verify the saved mission loads in DCS. Do not assume a plausible
  frequency is valid just because it is accepted by the Python API.

## Verification

- Run the relevant tests and generate the affected mission before handing off
  changes when the required map overlay and dependencies are available.
- Check every loadout against the exact DCS aircraft module: verify each store
  is on a station that module actually uses, not merely one pydcs accepts. When
  a DCS install is available, run the mission audit/loadout check against ED's
  shipped payload tables; otherwise inspect the aircraft's `PylonN` definitions
  and report that the in-game station check could not be run. Also confirm the
  briefing describes the stores that are actually loaded.
- Generate a mission explicitly to a workspace output directory, for example:
  `uv run dcs-mission-creator generate <slug> --output-dir out/<slug>`.

## Map-overlay data locations

- Build overlays with `uv run dcs-mission-creator map-overlay build <theater>
  --layers all`. Generated overlay data lives under
  `src/dcs_mission_creator/resources/overlays/<theater>/`; build inputs and
  cached data live under
  `src/dcs_mission_creator/resources/_build_cache/<theater>/`.
