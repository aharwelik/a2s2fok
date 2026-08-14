# Comma 4 / MICI compatibility

## Selected assumptions

- Base root branch: `d412k5t412/sunnypilot:subaru-gen2angle`.
- MICI comparison refs:
  - `sunnypilot/sunnypilot:release-mici` at `af744c85e7c971e7bfbc8e6ee9e2bd75452a6f00`.
  - `sunnypilot/sunnypilot:release-mici-staging` at `80fde1f3f3152d8d0165c2e69d62ce61608b0332`.
- Current base already contains MICI UI modules and updater routing.

## Repository redirect

The `aharwelik/openpilot` rename cycle was exercised. GitHub currently resolves
`/repos/aharwelik/openpilot` to the same repository object as
`aharwelik/sunnypilot`.

## Tests

The branch includes:

- `scripts/ascent/run_combined_v6_tests.sh`
- `scripts/ascent/audit_combined_v6_isolation.py`
- MICI HUD and settings import smoke through the Ascent V6 status constants.
- Canonical `scons -j8` build in the combined runner.

Hardware-only comma 4 boot validation is not run in this local workspace.
