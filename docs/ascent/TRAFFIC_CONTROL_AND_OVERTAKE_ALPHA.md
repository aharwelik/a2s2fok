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

Add saved qlogs to the same offline report with:

`python3 tools/ascent_v8_evidence.py --labels <private-labels.jsonl> --qlog-root <saved-realdata-directory> --output <private-report.json> <calibration-journal.jsonl>`

The extractor reports lead loss, physical braking, model/planner stop timing, and whether comma longitudinal control
was active. Every candidate remains `unreviewed` until a confirmed road-camera label matches the route and stop time;
pending or distant labels are not counted. It does not infer that a stop was caused by a sign or signal from braking
telemetry alone. Confirmed lead, cross-traffic, and parking/turn maneuver stops are tracked separately so they cannot
inflate traffic-control coverage. The report also groups model, planner, longitudinal-active, and brake-output responses
by confirmed cause, providing a replay baseline for later builds.

The qlog replay path is also non-actuating. It finds sustained curves above 0.003 1/m at speeds of at least 3 m/s,
uses 0.002 1/m hysteresis and a one-second minimum duration, and records entry/minimum speed, current curvature,
lateral acceleration, the existing 1.6 m/s2 standard curve-speed target, lane-line confidence, physical braking,
driver steering override, controller saturation, and blinker presence. A blinker only marks a curve with a turn signal;
it is not treated as proof of an intersection turn. Planner lead/deceleration timing is context, not traffic-control
detection. Only model/planner stop intent before standstill counts as a stop response.

The first saved route establishes a miss baseline, not a success claim. Across two confirmed stop signs and three
confirmed red signals, neither model stop intent nor planner stop intent appeared before standstill, comma longitudinal
was inactive, and comma emitted no brake output. The driver braked before all five, with a 3.546-second/21.652-meter
median lead over the combined traffic-control set. Three approaches contained a tracked lead; the median final lead
loss was 4.313 seconds before standstill. The separately confirmed stopped-lead case had planner lead/deceleration
context, but planner `shouldStop` did not precede standstill and the driver supplied the stop.

The second real driving route adds three video-confirmed ego-facing stop-sign approaches. All three were rolling
incomplete stops; two reviewed minimum speeds were about 1.90 m/s and 1.84 m/s. Its one full standstill was caused by
a small red cross-traffic vehicle roughly 20 seconds before the third sign. Video therefore changes the causal label
from an apparent sign stop to `cross_traffic_stop`. Across the two reviewed real routes, independent video coverage is
now 5 stop-sign and 3 signal approaches on 2 routes, still far below the 25-route/300+300 qualification gate.

The 28 saved qlogs produced 34 curve candidates: 7 had a blinker present, 15 included driver braking, 26 included a
driver steering override, 9 included controller saturation, and 5 exceeded the standard lateral-acceleration target
at peak curvature. These are replay candidates, not video-confirmed turn labels. Thirty-two contained at least one
sample where the conservative minimum of the two lane-line probabilities fell below 0.5, so any later curve-speed
controller must reject weak geometry instead of treating the current event set as ready for actuation.

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

An isolated COCO-pretrained YOLO26n qcamera baseline confirmed the expected object in two consecutive 2 Hz frames on
all five first-route approaches, but only one of five confirmations occurred by 40 m and none of the two stop signs did.
It classified neither signal phase nor ego relevance. This is useful as a crop/proposal baseline only; it fails the
early-distance requirement and must not feed a stop target. The next offline iteration needs full-resolution tiled
crops, temporal tracking, a separately validated red/yellow/green classifier, and local fine-tuning rather than a lower
confidence threshold.

The five corresponding 1344x760 `fcamera.hevc` segments were later copied read-only and replayed with the same object
model over the full frame plus two overlapping 760-pixel tiles. Object proposals moved earlier: the stop signs confirmed
at 40.607 m and 19.863 m, while the three signal objects confirmed at 74.035 m, 44.687 m, and 126.062 m. Conservative
phase-only red evidence confirmed at 32.555 m, 2.762 m, and 27.975 m. Requiring two same-phase heads as a weak
ego-relevance candidate remained later still: 6.319 m, 2.762 m, and 23.656 m. One route correctly produced a stable
two-head yellow candidate at 25.595 m followed by red at 2.762 m. These image-position heuristics are not ego-lane
ground truth.

Those distances are still too late for smooth stopping. With zero processing/actuation latency, a 1.5 m/s2 maximum
deceleration, and the existing 1.0 m/s3 command ramp, all five state/relevance-candidate confirmations had negative
stopping-distance margin: -5.499 m, -14.279 m, -16.958 m, -3.214 m, and -5.405 m. This is an optimistic lower bound;
measured latency would make it worse. Full-resolution object proposals are now early enough on several signals, so the
next bottleneck is earlier phase and ego-path ownership. Both stop signs still need earlier locally fine-tuned detection.

An object-only scan then sampled all 28 qcamera segments at 1 Hz over 10.020 km, rather than looking only near the five
labeled stops. It recovered all five labeled controls in two consecutive frames. Manual review of its 31 low-threshold
runs found 21 real-control runs and 10 false runs. Eight of the false runs were stop-sign proposals on red street or
plaza banners, a blue informational sign, and a yellow warning sign. At 0.25 confidence the scan retained all five known
controls but still retained two false stop-sign runs, equivalent to 19.960 reviewed false runs per 100 km on this route.
At 0.50 it removed every reviewed false run but lost the segment-2 stop sign. Confidence tuning alone therefore cannot
meet both recall and false-stop gates; the decoys are hard negatives for local fine-tuning and ego relevance.

The same scanner sampled 772 frames across all 13 segments of the second real route. Seven low-threshold runs reduced
to five true stop-sign runs covering three physical signs and two false runs. The false stop proposal on a vertical
roadside/tree object had 0.8659 confidence and survived the 0.50 threshold; meanwhile, two early fragments of the
shaded third sign remained below 0.25 and only its later close fragment reached high confidence. This independently
confirms that threshold tuning cannot provide both early recall and acceptable false-stop behavior.

The conservative HSV phase probe returned a color on only three of the 19 manually confirmed traffic-light runs: one
yellow and two green, all visually consistent; the other 16 remained unknown. Those qcamera crops were only 6-23 pixels
wide. This correctly avoids guessing but cannot provide usable phase coverage. Full-resolution segments 4, 5, 8, 9,
11, 15, 16, 17, and 18 are the next bounded recovery set once the device reports offroad.

A current OpenStreetMap snapshot was evaluated against 957 route GNSS fixes with at most 10 m reported accuracy.
All three labeled red signals matched a `highway=traffic_signals` node within 19.699-38.983 m, but neither stop sign
matched: the nearest `highway=stop` nodes were 490.730 m and 933.633 m away. Across the driven path, 26 signal nodes
and zero stop nodes were within 30 m. OSM therefore helps anticipate signalized intersections on this route but cannot
cover its stop signs or supply phase. [OSM signal](https://wiki.openstreetmap.org/wiki/Traffic_light) and
[stop](https://wiki.openstreetmap.org/wiki/Tag%3Ahighway%3Dstop) nodes are position features; approach direction,
lane ownership, stop line, and camera agreement remain required.

Reproduce this offline-only report from the saved full-resolution segments with:

`uv run --python 3.12 --with ultralytics python tools/ascent_v8_perception_replay.py --labels <private-labels.jsonl> --journal <calibration.jsonl> --realdata <saved-realdata> --model <pinned-model.pt> --output <private-report.json>`

Scan every saved qcamera segment for review candidates with:

`uv run --python 3.12 --with ultralytics python tools/ascent_v8_route_scan.py --video-root <saved-realdata> --model <pinned-model.pt> --output <private-scan.json>`

When the root contains several routes, pass `--route <route-id>`; the scanner now rejects an ambiguous mixed root.

Evaluate a saved OSM node snapshot against route GNSS and confirmed labels with:

`.venv/bin/python tools/ascent_v8_map_prior.py --qlog-root <saved-realdata> --labels <private-labels.jsonl> --osm <osm-controls.json> --output <private-map-report.json>`

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
