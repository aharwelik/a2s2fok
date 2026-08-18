# Ascent V8 traffic-control and overtake alpha

Research snapshot: 2026-08-17. Target: 2023 Subaru Ascent, comma four, V8 development branch.

## What is executable now

- `modelV2.action.shouldStop` and `desiredAcceleration` already feed openpilot's Experimental Mode longitudinal planner. The off-by-default **Ascent V8 model-stop evidence** developer toggle separately debounces that intent as `model_stop_prediction`, requires stopping corroboration, vetoes a nearby lead, a committed curve, stale inputs, and invalid trajectories, and records the result in `AscentV8ShadowStatus`.
- The off-by-default **Ascent V8 lane-change evidence** developer toggle records a slower lead, positive adjacent-lane geometry, lane confidence, road-edge/unknown-space classification, and BSM state. It becomes a `driver_left_lane_change_candidate` only after the driver confirms with the left blinker. It never operates a blinker or lane selection. The camera lane model does not identify same-direction versus opposing lanes or legal passing zones, so the output is deliberately not called pass-ready or permission to overtake.
- These features are evidence and replay surfaces. The 2023 Ascent still uses stock EyeSight for gas and brake, so model-stop evidence cannot command a stop in this version.

Both processes are ignored unless `CarParams.carFingerprint` is exactly `SUBARU_ASCENT_2023`; both toggles default false and are hidden on release builds.

Do not label `model_stop_prediction` as a red light or stop sign. The driving model predicts stopping behavior but does not publish a classified traffic-control object or signal phase.

## Why the actuator connector is not enabled yet

The 2023 Ascent is both Subaru Gen2 and angle-steering. The Subaru longitudinal implementation removed by [opendbc PR 3689](https://github.com/commaai/opendbc/pull/3689) did not make longitudinal available for either category. The PR specifically requires a characterized actuation API, speed-dependent limits inside the generic -3.5 to +2.0 m/s2 envelope, and a longitudinal maneuver report before re-enable.

There are additional vehicle-specific gaps:

- Gen2 receives `ES_Brake`, `ES_Distance`, and `ES_Status` on bus 1, but the dormant controller emits brake/status on bus 0. The old Panda allowlist expected bus 1.
- Disabling EyeSight removes camera-derived engagement/button inputs. The old Gen2 proof-of-concept polled DID `0x1130`, but did not finish parsing or assigning that response.
- Current angle safety RX checks require live camera messages that disappear when EyeSight communication is disabled.
- Reusing stock EyeSight while forging `ES_Distance` risks counter collisions; the current controller already documents that this can fault EyeSight and EPS.

A fake software lead is not a substitute. Stock EyeSight does not consume openpilot's `radarState`, and `Close_Distance` is an EyeSight output/display field, not a demonstrated controller input.

## Most plausible direct-long sequence

1. Capture `0x220`, `0x221`, and `0x222` on every bus during stock SET/RESUME, following stop, hold, restart, gas override, and brake-at-standstill. Repeat with EyeSight communication disabled and capture DID `0x1130` responses.
2. Fit speed-binned throttle, RPM, and brake envelopes from the exact Ascent logs. Keep every mapped command inside -3.5 to +2.0 m/s2.
3. Enable alpha long only for `SUBARU_ASCENT_2023`, only on development builds, and only through the existing off-by-default `AlphaLongitudinalEnabled` toggle.
4. Route angle `0x124` on bus 0, longitudinal `0x220/221/222` on bus 1, and the narrow tester-present/button UDS allowlist on bus 2.
5. Add a `GEN2 | LKAS_ANGLE | LONG` Panda test class with speed-bin boundary rejection, driver gas/brake override, inactive-output behavior, UDS allowlist coverage, and byte-for-byte unchanged angle output.
6. Prove model action -> Experimental planner -> `CC.longActive` -> CAN command -> measured vehicle deceleration, standstill hold, and resume.

This is the only researched route with a credible chance of making a no-lead traffic-control stop. ACC cancel can only coast. Cruise-button overlays can lower stock set speed but cannot demonstrate a controlled stop below the OEM minimum.

## Independent detector research

The independent Fable/Claude review recommended a high-resolution tiled lightweight detector, crop-based signal-state/relevance classifier, temporal tracker, calibrated stop-line range, and cached OpenStreetMap prior. Waze is not a traffic-control inventory or live signal-phase source; its developer feeds cover navigation links, incidents, closures, and partner vehicle data.

Possible research datasets have important scope limits:

- [Bosch Small Traffic Lights](https://hci.iwr.uni-heidelberg.de/node/6132) provides 13,427 images and roughly 24,000 state labels, but is non-commercial and explicitly not intended to cover production cases.
- [BDD100K](https://bdd-data.berkeley.edu/download.html) is useful for general driving research, but exact imagery/checkpoint terms must be tracked separately from the BSD-licensed toolkit.
- Self-collected, authorized Ascent logs are the only proposed primary release-validation source matching this camera, mounting, geography, and vehicle.

No second GPU daemon should be added without a comma-four measurement. Chestnut's USB GPU is already owned by `modeld`; any later detector must first prove latency and thermal headroom or be co-scheduled inside that runtime.

## More-likely-than-not qualification gate

No percentage is assigned from code inspection. Call the feature more likely than not to work only after a held-out, route-level evaluation with at least 25 routes, 300 stop-sign approaches, 300 signal approaches, and at least 50 night/rain/glare/occlusion examples per control type. Adjacent frames from one approach must not be split across train and test.

The lower bound of a route-bootstrap 95% confidence interval must clear all of these:

- stop-event recall at least 90% by 40 m and 80% by 60 m;
- ego-relevant signal recall at least 90% by 40 m;
- signal-state macro F1 at least 0.95 and red-as-green at most 0.5% of red approaches;
- confirmed false stop tracks at most 1 per 100 km;
- median stop-distance absolute error at most 3 m and 90th percentile at most 5 m from 10-50 m;
- confirmation within 1 second, stale/unknown output on disagreements, and monotonic approach distance on at least 95% of confirmed tracks;
- zero added model frame drops and no more than 1% modeld p95 latency regression over a 60-minute replay;
- direct-long closed-course proof for speed bins, stop, hold, resume, gas override, brake override, and unchanged angle/lane-change behavior.

The early detector kill criterion is less than 50% event recall by 40 m on ten local routes. If that occurs, stop tuning generic checkpoints and collect/fine-tune local data.

## Fork findings

- [StarPilot](https://github.com/prodigz/StarPilot/blob/9e3ab90bdd0c5fa539f7510f2a30f563bdc545ef/starpilot/controls/lib/conditional_experimental_mode.py) has the best MIT-licensed model-horizon hysteresis and tests found in the review. V8 reuses the design principle, not its source.
- [Carrot](https://github.com/ajouatom/openpilot/blob/f1be8e9821aaef361cf39136f31649a24837246a/openpilot/selfdrive/carrot/carrot_functions.py) has active model-horizon stop/go and speed capping, but its external signal data is not wired to a stop target.
- EnhancedOpenPilot has explicit YOLO/light-state code, but the audited planner does not subscribe to its `groundObjects` output and its perception stack targets RK3588 stereo/NPU hardware, not comma four.
- FrogPilot uses map intersection metadata to select Experimental Mode; it does not determine live signal color or prove stopping.

The repository-wide automated web workflow gathered 100 pages but its terminal evidence gate reported zero surviving options because most gathered pages were irrelevant. Those results were excluded; this decision uses pinned source code, upstream PRs/commits, official project pages, and the independent review above.
