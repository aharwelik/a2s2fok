# Ascent V8 model-stop and controlled-lot obstacle-bypass alpha

Research snapshot: 2026-08-17. Target: 2023 Subaru Ascent, comma four, V8 development branch.

## What is executable now

- `modelV2.action.shouldStop` and `desiredAcceleration` already feed openpilot's Experimental Mode longitudinal planner. The off-by-default **Ascent V8 model-stop evidence** developer toggle separately debounces that intent as `model_stop_prediction`, requires stopping corroboration, vetoes a nearby lead, a committed curve, stale inputs, and invalid trajectories, and records the result in `AscentV8ShadowStatus`.
- The off-by-default **Ascent V8 obstacle-bypass evidence** developer toggle records a slower obstacle/lead, positive adjacent corridor geometry, lane confidence, road-edge/unknown-space classification, and BSM state. It becomes a `driver_left_lane_change_candidate` after the left blinker confirms the controlled-lot maneuver. Sunnypilot's existing lane-change planner then performs the lateral move.
- The exact-Ascent alpha longitudinal connector now makes the existing Experimental Mode model-stop path testable end to end. It disables EyeSight communication, reads SET/RESUME/CANCEL from DID `0x1130`, routes `0x220/0x221/0x222` on Gen2 bus 1, and ramps deceleration progressively at 1.0 m/s3.

Both processes are ignored unless `CarParams.carFingerprint` is exactly `SUBARU_ASCENT_2023`; both toggles default false and are hidden on release builds.

Do not label `model_stop_prediction` as a red light or stop sign. The driving model predicts stopping behavior but does not publish a classified traffic-control object or signal phase.

## How to exercise the alpha connector

1. Enable **Alpha longitudinal** and **Experimental Mode**, then reboot the device with ignition on before engine start so early EyeSight communication control can complete.
2. Press and release SET or RESUME to engage the non-PCM cruise path. The main/cancel button disengages it.
3. Present a controlled-lot stop-sign/light scenario. The normal model `shouldStop` and `desiredAcceleration` signals feed the longitudinal planner and the Subaru controller's gradual command ramp.
4. For the obstacle bypass, enable **Ascent V8 obstacle-bypass evidence**, wait for left-corridor readiness, then use the left blinker. Use the right blinker after the obstacle for the normal return lane change.

## Automatic first-drive data

No recording toggle is required. On every exact 2023 Ascent drive, V8 writes a 10 Hz calibration journal under
`/data/ascent_maintenance/calibration`. It pairs vehicle speed/acceleration and road pitch with the model stop request,
longitudinal plan, requested/applied actuators, physical buttons, and the derived Subaru throttle/RPM/brake commands.
The normal logger simultaneously retains the full route rlog, byte-for-byte CAN history, and road-camera video. The
recorder also marks that route for the normal qlog/qcamera upload queue so its route identifier and preview video are
available remotely when connectivity is present.

After the drive, download the calibration journal and its route identifier with:

`./tools/ascent_v8_ssh.py <device-ip-or-name> logs --output ~/Downloads/ascent-first-drive.tar.gz`

After extracting the bundle, inventory candidate stops with:

`python3 tools/ascent_v8_evidence.py <extracted-directory>/calibration/*.jsonl`

Keep manual labels outside the source tree and merge only video-confirmed entries with:

`python3 tools/ascent_v8_evidence.py --labels <private-labels.jsonl> <extracted-directory>/calibration/*.jsonl`

Add `--output <private-report.json>` to save the merged report without copying private labels into the repository.

The extractor reports lead loss, physical braking, model/planner stop timing, and whether comma longitudinal control
was active. Every candidate remains `unreviewed` until a confirmed road-camera label matches the route and stop time;
pending or distant labels are not counted. It does not infer that a stop was caused by a sign or signal from braking
telemetry alone. Confirmed lead, cross-traffic, and parking/turn maneuver stops are tracked separately so they cannot
inflate traffic-control coverage. The report also groups model, planner, longitudinal-active, and brake-output responses
by confirmed cause, providing a replay baseline for later builds.

The recorder keeps the newest eight journals within a 256 MiB cap, and the SSH bundle automatically includes them.

Implemented vehicle-specific pieces:

- `ES_Brake`, `ES_Distance`, and `ES_Status` transmit on bus 1 for Gen2; angle steering remains `0x124` on bus 0.
- DID `0x1130` responses are parsed into physical SET/RESUME/CANCEL events in both CarState and Panda.
- The combined `GEN2 | LKAS_ANGLE | LONG` Panda mode uses a direct-long RX set that does not require silent EyeSight output frames.
- A cached exact-Ascent fingerprint triggers the proven early communication-control sequence before fingerprinting, followed by tester-present keepalive.
- The actuator command changes at no more than 1.0 m/s3 toward braking and 1.5 m/s3 toward acceleration.

A fake software lead is not a substitute. Stock EyeSight does not consume openpilot's `radarState`, and `Close_Distance` is an EyeSight output/display field, not a demonstrated controller input.

## Current proof status

The exact vehicle gate, toggle behavior, DID button parser, combined Panda mode, CAN buses, command bounds, cancel behavior, and progressive brake ramp have automated coverage. The remaining proof is on the physical Ascent: record model action -> Experimental planner -> `CC.longActive` -> bus-1 command -> measured deceleration, standstill hold, and resume. Those logs will also replace the inherited raw throttle/RPM/brake interpolation with Ascent-specific speed-binned points if the measurements differ.

This direct-long route is the researched way to make a no-lead model stop. ACC cancel only coasts, and cruise-button speed reduction cannot reach a controlled zero-speed stop below the OEM set-speed floor.

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
