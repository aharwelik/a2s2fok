# Ascent V6 test report

## Current verified results

- OpenDBC full `./test.sh`: PASS.
- OpenDBC focused Subaru safety and Ascent V6 tests: PASS.
- Root static isolation audit: PASS.
- Root stop-obstacle deterministic tests: PASS, 16 passed.
- Root overtake-advisor deterministic tests: PASS, 10 passed.
- Root map regression test from Sunnypilot PR #1816: PASS, 5 passed.
- Root planner/button tracker tests from Sunnypilot PR #1893: PASS, 6 passed.
- Root speed-limit button integration tests: PASS, 25 passed.
- Root lane-change and lane-turn state tests: PASS, 48 passed.
- Root UI status import smoke: PASS.
- Root comma 4 / MICI import smoke: PASS.
- Root canonical `scons -j8` build: PASS.
- Public recursive clone: pending after root push.
- Installer endpoint: pending after root push.
- Route replay: NOT_RUN; private routes are not present in this workspace.

## Road validation

No live 2023 Ascent road validation has been performed by this build process.
