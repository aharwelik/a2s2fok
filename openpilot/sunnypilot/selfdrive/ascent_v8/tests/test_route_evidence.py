import json

from openpilot.sunnypilot.selfdrive.ascent_v8.route_evidence import analyze_files, stop_candidates


def sample(second: float, speed: float, *, brake=False, lead=None, model_stop=False, plan_stop=False,
           long_active=False, output_brake=0.0):
  return {
    "mono_ns": int(second * 1e9),
    "vehicle": {"v_ego": speed, "brake_pressed": brake},
    "model": {"should_stop": model_stop},
    "plan": {"should_stop": plan_stop},
    "control": {"long_active": long_active, "output_brake": output_brake},
    "evidence": {"lead_distance_m": lead},
  }


def test_lead_turns_away_and_model_stop_arrives_after_manual_stop():
  samples = [
    sample(0, 11.0, lead=18.0),
    sample(1, 8.0, lead=12.0),
    sample(2, 5.0),
    sample(3, 2.0, brake=True),
    sample(4, 0.0, brake=True),
    sample(5, 0.0, brake=True, model_stop=True),
  ]

  assert stop_candidates("route", samples) == [{
    "route": "route",
    "stopped_mono_ns": 4_000_000_000,
    "approach_speed_mps": 11.0,
    "driver_braked": True,
    "lead_seen": True,
    "lead_lost_before_stop_s": 3.0,
    "model_stop_while_moving": False,
    "first_model_stop_relative_s": 1.0,
    "planner_stop": False,
    "comma_longitudinal_active": False,
    "comma_brake_output": False,
    "label": "unreviewed",
  }]


def test_standstill_frames_do_not_duplicate_candidates():
  samples = [sample(0, 6.0), sample(1, 0.2), sample(2, 0.0), sample(3, 0.1)]
  assert len(stop_candidates("route", samples)) == 1


def test_analyze_files_reports_coverage(tmp_path):
  journal = tmp_path / "route.jsonl"
  rows = [{"schema": 1, "kind": "ascent_v8_calibration", "route": "route-a"}, sample(0, 6.0), sample(1, 0.0)]
  journal.write_text("".join(json.dumps(row) + "\n" for row in rows))

  result = analyze_files([journal])

  assert result["routes"] == [{"route": "route-a", "samples": 2, "candidate_stops": 1}]
  assert result["coverage"]["recorded_journals"] == 1
  assert result["coverage"]["unreviewed_stop_candidates"] == 1
  assert result["coverage"]["qualified_routes"] == 0
