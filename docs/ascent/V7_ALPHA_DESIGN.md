# 2023 Subaru Ascent V7 Alpha

This branch starts from root `78965b9f8293fb290eda6abf17dd61f4b932c94e` and OpenDBC
`4e7bad36b655da342a773d4ad6ff799838ab4a55`. It is a controlled-course alpha,
not a claim of completed on-vehicle validation.

## Active release boundary

- The complete V6 AnglePlanner and its 170/300/100 driver thresholds remain in place.
- ES_LKAS_ANGLE is transmitted only on bus 0. Bus 2 and dual-bus steering are rejected.
- Stock EyeSight owns longitudinal control, automatic emergency braking, and forward-collision warning.
- Driver-requested lane changes remain the only physical pass/return action.
- Stop, queue, curve, map, navigation, speed-limit, EPS-conflict, and ownership features are advisory or shadow only.
- Direct longitudinal and traffic-control alpha defaults are literal `False`, their runtime is compiled out,
  and the V7 research package contains no CAN, Panda mutation, or ECU-disable calls.

## V7 release changes

- Driver-yield resume no longer depends on a planner target the inactive EPS cannot reach. Resume retains the
  V6 hold, requires two consecutive frames at or below 3 degrees/second, and anchors the first request to measured angle.
- Independent MADS steering requires a valid Panda state and `ENABLE_MADS`; a fresh request clears stale heartbeat debt.
- Generic cruise cancel is suppressed only while not engageable during the first 10 seconds of boot.
- Speed-cap acceleration is clamped so a cap cannot inject more-positive acceleration than actual vehicle acceleration.
- Pass advice now vetoes road-edge, unknown occupancy, navigation contradiction, and invalid driver-monitoring state.
- Passive bounded EPS-conflict and steering-ownership analyzers expose no actuation path.
- Direct-long capability states and local gap recording are present for future evidence, but physical runtime remains blocked.

## Primary source locks inspected

- Physical Ascent OpenDBC PR 2217, head `556f8ed1c7eac63fe72e0a92047134d76dade721`.
- Modern angle safety PR 3454, head `6323695c6f1abab27512d5e3a54cd5316f08f8a9`.
- nl1031 hard-yield `6e5139d05af7011ce5fdef9d48b8704dc1ff2b2d` and MADS sync
  `83c3972b292fbfd281568e10bb4f15ffdcfc57df`.
- StarPilot exact-Ascent settle `ede63179c19ebd8cf4568e741a10cce5a2b100b2`.
- Sunnypilot MADS root guard `d7ece740d63858b1e9fd3a5e7cfd898b72ca4124`, heartbeat PR 493 head
  `aba9aeefa96cf56cf6509a25e1f16c80e636d16e`, and boot guard PR 1909 head
  `429cb3889b8aa5e2797ac5382f4e866951850f42`.
- Old Gen2 long PR 30372 head `c261ed1` and EyeSight disable PR 30373 head `87553f5` were inspected.
- mpurnell1 `subaru-angle-steering` research was inspected as evidence only; its raw Panda/CAN research scripts were not ported.

The automated broad web-research run completed mechanically but did not promote a source-backed implementation option.
The changes above therefore use exact primary Git refs plus deterministic repository tests.

## Explicitly unproven or blocked

- No private Ascent route was available for process replay.
- No comma 4 device build, indoor boot, parked diagnostic test, crank survival test, or low-speed vehicle test ran here.
- Pre-engine EyeSight disable, replacement-message runtime, and Ascent Panda longitudinal actuation are not implemented.
- Direct-long and stop-sign/red-light physical braking cannot activate in this build.
- A successful macOS host build is not comma 4 installability proof and does not authorize a device wipe.

Run `scripts/ascent/run_v7_alpha_tests.sh` from a complete recursive checkout. The report is written to
`artifacts/ascent_v7_test_report.json`.
