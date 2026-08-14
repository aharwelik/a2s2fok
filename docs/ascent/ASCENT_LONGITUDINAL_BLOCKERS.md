# Ascent longitudinal blockers

The 2023 Ascent remains stock-EyeSight-longitudinal only in this branch.

Blocking reasons:

- The selected Subaru Gen2 LKAS-angle safety configuration excludes
  openpilot longitudinal for `GLOBAL_GEN2` and `LKAS_ANGLE`.
- OpenDBC tests prove `SUBARU_ASCENT_2023` has
  `alphaLongitudinalAvailable == False`.
- OpenDBC tests prove `openpilotLongitudinalControl == False` for the 2023
  Ascent even when `alpha_long=True` is requested.
- `DISABLE_EYESIGHT` is not set for this platform.
- No live Ascent validation exists for openpilot brake or throttle commands.

The stop-obstacle package is therefore live-shadow only. It can mutate planner
obstacles only under replay/simulation runtime proof.

