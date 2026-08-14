# Combined V6 source lock

Retrieval UTC: 2026-08-04T15:42:12Z

GitHub login: `aharwelik`

## Target repositories

| Repository | Visibility | Fork | Default branch |
| --- | --- | --- | --- |
| `aharwelik/sunnypilot` | public | yes | `subaru-gen2angle` |
| `aharwelik/sunnyopendbc` | public | yes | `master` |

The requested `aharwelik/openpilot` repository-name redirect was exercised by
renaming `aharwelik/sunnypilot` to `openpilot` and back to `sunnypilot`.
`GET /repos/aharwelik/openpilot` currently resolves with HTTP 200 to the same
repository object (`id R_kgDOTt0RQA` / numeric id `1323110720`), now named
`aharwelik/sunnypilot`.

## Selected bases

| Source | Branch/ref | SHA | Notes |
| --- | --- | --- | --- |
| `d412k5t412/sunnypilot` | `subaru-gen2angle` | `3f5708b4445f2e39df4135b71c06fdbd88a6a143` | Selected root base. Includes the August 3 update to the OpenDBC submodule. |
| `d412k5t412/sunnyopendbc` | `subaru-gen2angle` | `49d55a02f5092085f6bb894f44ea230a69cf9185` | Selected OpenDBC base. Contains `DRIVER_OVERRIDE_TORQUE = 170`. |
| `sunnypilot/sunnypilot` | `master` | `1a07e4722853c0606b0e1caa8f300a371e342948` | Upstream comparison base. |
| `sunnypilot/opendbc` | `master` | `4c64e8a95b4eadca6a9e631d06a854f52bb9ebfa` | Upstream OpenDBC comparison base. |
| `commaai/opendbc` | `master` | `1bacd87e5aee0abb7dc5b3fdee41382f8032f639` | Comma upstream OpenDBC comparison base. |

The root OpenDBC submodule at source lock is
`49d55a02f5092085f6bb894f44ea230a69cf9185`.

## Required upstream fixes and references

| Item | State observed | SHA / ref |
| --- | --- | --- |
| SCC map quadratic-root fix, Sunnypilot PR #1816 | merged 2026-07-25T13:37:19Z | `fd22de1c9aa88e0ad02549ff27d62d05394417c9` |
| planner/button event fix, Sunnypilot PR #1893 | merged 2026-08-02T03:05:03Z | `978ec800fead1b34c4e43ebc69fb92b67695bdf0` |
| MADS heartbeat reset, Sunnypilot OpenDBC PR #493 | open draft | `aba9aeefa96cf56cf6509a25e1f16c80e636d16e` |
| Comma Subaru LKAS angle, OpenDBC PR #3454 | open | `6323695c6f1abab27512d5e3a54cd5316f08f8a9` |
| Historical Ascent LKAS angle, OpenDBC PR #2217 | closed | `556f8ed1c7eac63fe72e0a92047134d76dade721` |
| CarrotPilot stop/overtake reference | pinned reference | `9607683a21fe553ae500d019af89697ce0e28f1d` |
| FrogPilot UI/map reference | pinned reference | `1e23dec6352cef5a36a87be0af7d7a082b7c48a4` |

## Comma 4 / MICI comparison refs

| Source | Branch | SHA |
| --- | --- | --- |
| `sunnypilot/sunnypilot` | `release-mici` | `af744c85e7c971e7bfbc8e6ee9e2bd75452a6f00` |
| `sunnypilot/sunnypilot` | `release-mici-staging` | `80fde1f3f3152d8d0165c2e69d62ce61608b0332` |

## Movement from prompt locks

- The selected root base matches the prompt lock:
  `3f5708b4445f2e39df4135b71c06fdbd88a6a143`.
- The selected OpenDBC base matches the prompt lock:
  `49d55a02f5092085f6bb894f44ea230a69cf9185`.
- Upstream Sunnypilot `master` matches the prompt lock:
  `1a07e4722853c0606b0e1caa8f300a371e342948`.
- The August 3 driver-takeover threshold update is viable as the integration
  base because it is already in the selected root and OpenDBC heads.

## Target branch pre-state

- `origin/ascent-2023-combined-test-v6`: absent at source-lock time.
- `origin/ascent-2023-combined-opendbc-v6`: absent at source-lock time.

