# Ascent V8 next-build backlog

This is the ordered backlog for the next signed build. Nothing in this document is permission to deploy or actuate on
public roads. EyeSight AEB/lane safety and driver monitoring stay enabled. Vehicle-impact changes remain parked,
replay, controlled-course, and physical-device gated.

## P0 - evidence must never be blocked by the mutation gate

- Keep update, rollback, service restart, and vehicle-control changes behind the strict parked/offroad/disengaged gate.
- Add a separate non-mutating live evidence path. It may read the active calibration journal and copy only closed qlog
  and qcamera segments; it must not compress on-device, restart services, write Params, or contend with modeld.
- Add an event-bookmark command that records synchronized host UTC, device monotonic time, current route, segment,
  and the driver's short label while driving. A delayed report must be searched across adjacent segments before it is
  assigned to a frame.
- Mirror closed lightweight segments opportunistically over the local hotspot and resume by checksum after a network
  interruption. Full-resolution rlog/fcamera data remains on-device and follows the normal uploader path.
- Split evidence-export policy from mutation policy. `ControlsReady` persists after a drive by design and must not
  prevent read-only export, but it must continue to block update/restart/deploy operations.
- Automatically merge only video-confirmed labels. Pending, mismatched, and telemetry-only labels never count toward
  detector coverage.

## P0 - lead following and intersection ownership

- Continue normal radar/model lead following while the lead is stable and in the ego path.
- Smoothly stop behind a stationary lead with time-gap, standstill hold, brake override, and resume coverage.
- When a lead turns away or is lost near an intersection, never inherit that vehicle's right-of-way. Freeze the last
  lead as uncertain briefly, then require the ego vehicle's own signal/sign/path evidence.
- Never infer a green light because a lead moved, or infer a turn merely because a blinker is active. The blinker is a
  driver intent hint, not an autonomous intersection-turn command.
- Replay cut-in, lead-turn-away, stopped-lead, lead-resume, and red-light-behind-lead cases before controlled-course
  testing.
- Use the saved-route timing baseline: the stopped-lead case had planner lead/deceleration context, but planner
  `shouldStop` did not precede standstill, comma longitudinal was inactive, and the driver supplied the stop.

## P0 - stop signs and red lights

- Preserve the completed manual review of all ten first-route stop candidates: two stop signs, three red signals, one
  stopped-lead queue, one pedestrian/cross-traffic stop, and three parking/turn maneuvers.
- Build a camera-first pipeline: high-resolution traffic-control crops, sign/signal classification, ego relevance,
  temporal tracking, calibrated distance/stop-line estimation, and stale/unknown output on disagreement.
- Treat the driving model's `shouldStop` as corroborating intent only. It is not a sign classifier or signal-phase
  label.
- Generate a jerk-limited stop target with comfortable early deceleration, a full legal stop, standstill hold, and
  immediate driver gas/brake override. No public-road actuation before replay and closed-course gates pass.
- Keep separate labels for stop sign, signal phase, yield, lead-caused stop, cross-traffic, and driver-choice stop so
  braking telemetry cannot create false traffic-control ground truth.
- Treat the first saved route as five confirmed traffic-control misses: zero model/planner stop responses before
  standstill and zero comma brake outputs across two stop signs and three red signals. The driver's median intervention
  lead was 3.546 seconds and 21.652 meters; these values are a comparison baseline for later replay builds.
- Do not promote the generic COCO object baseline. It eventually confirmed all five expected objects, but only one by
  40 meters, no stop signs by 40 meters, and no signal phase or ego relevance. Use it only to propose high-resolution
  crops for the camera-first detector.
- Use the full-resolution tiled replay as the new baseline. It moved signal-object proposals to 44.687-126.062 meters
  and one stop sign to 40.607 meters, but red phase evidence remained at 2.762-32.555 meters, conservative two-head
  relevance candidates remained at 2.762-23.656 meters, and all five controls had negative jerk-limited smooth-stop
  margin even with zero latency. Improve phase/ownership first; locally fine-tune both stop-sign approaches for earlier
  confirmation.
- Add measured camera, detector, planner, and Subaru-command latency to the jerk-limited stop-distance gate. A replay
  candidate is not stop-ready unless its worst-case margin remains nonnegative after that latency and uncertainty.
- Train and hold out the first-route hard negatives: red street/plaza banners, a blue informational sign, and a yellow
  warning sign. The generic detector at 0.25 retained all five known controls but still proposed two false stop signs in
  10.020 km; at 0.50 it removed reviewed false runs but missed a true stop sign. Do not solve this by threshold tuning.
- After the comma reports offroad, recover full-resolution route-4 segments 4, 5, 8, 9, 11, 15, 16, 17, and 18 for
  phase review. The qcamera probe produced only one yellow and two green outputs across 19 confirmed-light runs; 16
  stayed unknown because the crops were only 6-23 pixels wide.

## P1 - curves and turns

- Score every route curve using curvature, entry speed, lateral acceleration, lane/path confidence, driver braking,
  and steering saturation.
- Add an early, smooth curve-speed target bounded by lateral acceleration and jerk. Reject it when path geometry is
  unstable rather than producing an abrupt late slowdown.
- Navigation route intent may select the expected branch at an intersection, but it must not initiate a turn from a
  blinker or lead trajectory alone.
- Review and label the 34 first-route curve candidates. Seven merely had a blinker present and are not turn ground
  truth; nine included steering saturation, five exceeded the standard curve target at peak curvature, and 32 had at
  least one low-confidence lane sample. Reject weak geometry before tuning speed targets.

## P1 - Florida offline map and GPS fusion

- Use the comma's existing GNSS and `liveLocationKalman`; a phone GPS is not required for positioning.
- Configure sunnypilot mapd for a Florida-only offline OpenStreetMap download instead of the whole United States.
- Extend the offline map output with nearby stop-sign nodes, traffic-signal nodes, intersection topology, road class,
  speed limit, and turn geometry. Map controls are priors only because inventories can be missing or stale and maps do
  not provide live signal color.
- Fuse map topology with camera state, calibrated distance, route intent, and lead tracking. Camera disagreement or
  uncertain ego relevance must produce unknown, not a guessed stop/go decision.
- A phone navigation route can help with intended lane/turn and upcoming-intersection relevance, but it cannot provide
  reliable live signal phase. Define a narrow authenticated route-intent interface before adding phone dependency.
- Do not depend on the Subaru built-in map until an authorized, documented interface is proven. No current CAN signal
  establishes access to the head unit's map or route database.

## P1 - driver alerts and retained safety systems

- Preserve driver monitoring and its lockout behavior. Driver distraction did not cause the observed traffic-control
  misses.
- Preserve the steering-required alert. The observed factory hands-on-wheel message was the steering-saturation
  warning, not a driver-monitoring alert.
- Preserve stock EyeSight AEB and lane safety. Turning EyeSight features off does not add traffic-light perception.
- Make UI wording distinguish DMS, steering saturation, stock EyeSight, lead following, and experimental traffic
  control so the source of an alert is obvious.

## P2 - parked shutdown and battery protection

- Preserve the observed key-off/restart sequence as a power-state fixture. The first route ended with engine RPM near
  800, followed by the ignition-line falling edge. About 176 seconds later the line rose again, and raw Subaru
  `Throttle.Engine_RPM` rose from zero to cranking/idle about 0.834 seconds later. Treat that second route as an actual
  engine-running state, not a proven door-only false wake.
- The driver does not remember opening a door. CarState's aggregate `doorOpen` bit is not driver-door proof and must
  not be used to assign the cause of a wake or restart.
- Add engine RPM from the Subaru `Throttle.Engine_RPM` DBC signal to recorded car state and verify it against actual
  engine starts and stop/start operation.
- If an unexplained onroad transition recurs without raw engine RPM, capture the full CAN transition before designing
  any Ascent-specific wake filter. A real start must always win immediately; timing alone is never enough to suppress
  ignition.
- Verify that a true offroad state dims the display, enables panda power saving, stops route recording, and reaches
  hardware shutdown at the selected timeout.
- Change the Ascent package's offroad timeout from the current 30-hour default to a user-visible 5-30 minute choice,
  with 30 minutes as the initial conservative default. Validate wake-on-real-ignition and uploader completion before
  release.
- Add a parked power regression test: ignition and engine-RPM fall, route close, screen off, panda power save, measured
  draw, shutdown, cold wake, and no battery-warning event after an overnight park.

## Release proof gate

- Replay all saved routes without dropped frames and produce event-by-event confusion tables.
- Meet the route-level detector thresholds in `TRAFFIC_CONTROL_AND_OVERTAKE_ALPHA.md`; adjacent frames from one event
  stay in the same train/test split.
- Complete controlled-course tests for stopped lead, lead departure, stop sign, red/yellow/green relevance, rolling
  approach, stop/hold/resume, curves, driver overrides, and stale/unknown behavior.
- Complete the parked power test and a physical comma-four latency/thermal test.
- Build, audit, sign, publish, install only while the vehicle gate is safe, then verify the exact running commit and
  preserve a tested rollback.
