# Stop obstacle design

Package:

```text
sunnypilot/selfdrive/controls/lib/stop_obstacle/
```

The estimator accepts model stop intent, position/velocity profiles, ego state,
lead snapshots, override/fault flags, and source labels. It produces a
`StopTarget` with:

- validity
- confidence
- distance
- buffer
- time-to-stop
- minimum predicted speed
- required deceleration
- source
- state
- age
- rejection reason

Live mode is `LIVE_SHADOW`: compute, log, and display only. It does not mutate
`longitudinalPlan`, `CarControl`, cruise set speed, or outgoing vehicle-control
messages.

Simulation mode requires two independent proofs:

1. explicit `REPLAY_SIMULATION` mode;
2. runtime reports replay/simulation with no live vehicle attachment.

