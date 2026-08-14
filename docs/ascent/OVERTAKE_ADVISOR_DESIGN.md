# Overtake advisor design

Package:

```text
sunnypilot/selfdrive/controls/lib/overtake_advisor/
```

Live mode is advisory only. The advisor can emit:

```text
PASS POSSIBLE — SIGNAL REQUIRED
```

It does not activate blinkers, initiate a lane change, request a speed increase,
or chain an automatic return. Existing Sunnypilot lane-change code remains the
owner of driver-blinker lane changes.

Simulation mode can request a simulated lane-change transition only when replay
or simulator runtime proof is present and no live vehicle is attached.

Rejection gates include stale model, blind spot, lane unavailable, driver brake,
driver gas, steering fault, and unexpected longitudinal ownership.

