import json
from types import SimpleNamespace as NS

from openpilot.sunnypilot.selfdrive.ascent_v8.calibration_recorder import (
  CalibrationRecorder,
  build_calibration_sample,
  subaru_longitudinal_command,
)


class FakeParams:
  def __init__(self):
    self.values = {"CurrentRoute": b"2026-08-18--first-drive", "GitCommit": b"abc123", "GitBranch": b"v8"}

  def get(self, key):
    return self.values.get(key)

  def put(self, key, value):
    self.values[key] = value


def test_build_sample_pairs_model_plan_vehicle_output_and_subaru_can():
  car_state = NS(
    vEgo=8.0, vEgoRaw=8.1, aEgo=-0.4, standstill=False, gasPressed=False, brakePressed=False,
    brakeHoldActive=False, cruiseState=NS(available=True, enabled=True, standstill=False),
    wheelSpeeds=NS(fl=8.0, fr=8.0, rl=8.0, rr=8.0), buttonEvents=[NS(type="setCruise", pressed=True)],
  )
  model = NS(frameId=42, big=True, action=NS(shouldStop=True, desiredAcceleration=-0.8, desiredCurvature=0.01),
             position=NS(x=[0.0, 30.0]), velocity=NS(x=[8.0, 0.0]))
  car_control = NS(enabled=True, longActive=True, orientationNED=[0.0, 0.02, 0.0],
                   actuators=NS(accel=-0.7, longControlState="stopping"))
  car_output = NS(actuatorsOutput=NS(accel=-0.6, gas=0.0, brake=0.3))
  plan = NS(longitudinalPlanSource="e2e", aTarget=-0.75, shouldStop=True, hasLead=False,
            allowThrottle=False, allowBrake=True, speeds=[8.0], accels=[-0.75], jerks=[-0.2])
  sample = build_calibration_sample(
    car_state, model, car_control, car_output, plan,
    shadow={"model_stop_prediction": True, "trajectory": "VALID"}, monotonic_ns=123,
  )

  assert sample["vehicle"]["pitch_rad"] == 0.02
  assert sample["model"]["path_end_m"] == 30.0
  assert sample["plan"]["source"] == "e2e"
  assert sample["control"]["output_brake"] == 0.3
  assert sample["subaru_command"] == {"throttle": 1818, "rpm": 600, "brake": 103}


def test_subaru_command_records_exact_lookup_boundaries():
  assert subaru_longitudinal_command(2.0, True) == {"throttle": 3400, "rpm": 3600, "brake": 0}
  assert subaru_longitudinal_command(-3.5, True) == {"throttle": 1818, "rpm": 600, "brake": 600}
  assert subaru_longitudinal_command(-1.0, False) == {"throttle": 1818, "rpm": 0, "brake": 0}


def test_recorder_starts_automatically_rate_limits_and_tracks_route(tmp_path):
  params = FakeParams()
  recorder = CalibrationRecorder(params, tmp_path)

  assert recorder.record({"mono_ns": 1}, 100_000_000)
  assert not recorder.record({"mono_ns": 2}, 150_000_000)
  assert recorder.record({"mono_ns": 3}, 200_000_000)

  path = tmp_path / "2026-08-18--first-drive.jsonl"
  rows = [json.loads(line) for line in path.read_text().splitlines()]
  assert rows[0]["kind"] == "ascent_v8_calibration"
  assert rows[0]["git_commit"] == "abc123"
  assert [row["mono_ns"] for row in rows[1:]] == [1, 3]
  assert params.values["AscentV8CalibrationStatus"]["route"] == "2026-08-18--first-drive"
  assert params.values["AthenadRecentlyViewedRoutes"] == "2026-08-18--first-drive"

  params.values["CurrentRoute"] = "second/route"
  assert recorder.record({"mono_ns": 4}, 300_000_000)
  assert (tmp_path / "second_route.jsonl").exists()
  assert recorder.status()["route"] == "second/route"
  assert params.values["AthenadRecentlyViewedRoutes"].split(",") == ["2026-08-18--first-drive", "second/route"]
