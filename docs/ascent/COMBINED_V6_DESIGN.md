# Ascent 2023 combined V6 design

## Selected base

The build starts from `d412k5t412/sunnypilot:subaru-gen2angle` at
`3f5708b4445f2e39df4135b71c06fdbd88a6a143` and uses the user-owned OpenDBC
branch at `aharwelik/sunnyopendbc:ascent-2023-combined-opendbc-v6`.

The August 3 OpenDBC update is included through the selected OpenDBC base:
normal driver steering override is `170`, blinker-active override is `300`, and
release remains below `100`.

## Live vehicle boundary

For `SUBARU_ASCENT_2023`, longitudinal ownership remains:

```text
LONGITUDINAL_OWNER=STOCK_EYESIGHT
```

The branch does not enable openpilot longitudinal control for the 2023 Ascent,
does not disable EyeSight, and does not add new Subaru brake/throttle authority.

## Root changes

- OpenDBC submodule now points to the user-owned OpenDBC V6 branch/SHA.
- SCC-M quadratic-root map fix from Sunnypilot PR #1816 is ported.
- Planner/button release bitmask fix from Sunnypilot PR #1893 is ported.
- Stop-obstacle research is implemented as an isolated live-shadow package.
- Overtake research is implemented as an isolated live-shadow advisor.
- MICI HUD renders `ASCENT V6 TEST — STOCK EYESIGHT BRAKING`.
- Static audit and combined V6 test runner are included under `scripts/ascent`.

## Simulation-only actuation

Stop-obstacle planner mutation and overtake lane-change requests are permitted
only when explicit replay/simulation mode is selected and runtime reports no
live vehicle attachment. Live mode computes telemetry and labels only.

