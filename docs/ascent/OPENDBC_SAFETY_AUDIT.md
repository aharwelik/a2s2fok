# Root OpenDBC safety audit

The root branch points `opendbc_repo` to:

```text
https://github.com/aharwelik/sunnyopendbc.git
ascent-2023-combined-opendbc-v6
4e7bad36b655da342a773d4ad6ff799838ab4a55
```

OpenDBC `./test.sh` passed after the V6 OpenDBC changes:

- ruff: passed
- ty: passed
- codespell: passed
- cpplint: passed
- MISRA safety check: passed
- unittest: 9346 passed, 1243 skipped

The root static isolation audit verifies the new stop/overtake packages do not
import vehicle-control modules or use prohibited live-actuation tokens.

