import json

from openpilot.sunnypilot.selfdrive.ascent_v7.direct_long_alpha import (
  DIRECT_LONG_ALPHA_DEFAULT,
  PANDA_LONG_RUNTIME_COMPILED,
  DirectLongDecision,
  DirectLongEvidence,
  DirectLongRecorder,
  DirectLongSample,
  DirectLongState,
  evaluate_direct_long,
  traffic_control_can_actuate,
  write_gap_report,
)


def test_direct_long_is_off_and_compiled_out_by_default():
  assert DIRECT_LONG_ALPHA_DEFAULT is False
  assert PANDA_LONG_RUNTIME_COMPILED is False
  decision = evaluate_direct_long(DirectLongEvidence())
  assert decision.state == DirectLongState.UNAVAILABLE
  assert not decision.long_can_allowed


def test_wrong_vehicle_fails_safe():
  decision = evaluate_direct_long(DirectLongEvidence(explicit_alpha_request=True))
  assert decision.state == DirectLongState.FAILED_SAFE
  assert decision.reason == "exact_vehicle_identity_required"


def test_engine_running_without_post_crank_proof_fails_safe():
  decision = evaluate_direct_long(DirectLongEvidence(
    explicit_alpha_request=True,
    exact_ascent_2023=True,
    ignition_on=True,
    engine_running=True,
  ))
  assert decision.state == DirectLongState.FAILED_SAFE
  assert decision.reason == "no_post_crank_disable_proof"


def test_complete_claim_still_fails_closed_while_panda_runtime_is_blocked():
  evidence = DirectLongEvidence(**{field: True for field in DirectLongEvidence.__dataclass_fields__})
  decision = evaluate_direct_long(evidence)
  assert decision.state == DirectLongState.FAILED_SAFE
  assert decision.reason == "panda_long_runtime_blocked"
  assert not decision.long_can_allowed


def test_traffic_control_cannot_actuate_in_blocked_build():
  claimed_ready = DirectLongDecision(DirectLongState.ALPHA_LONG_ACTIVE, True, "test_fixture")
  assert not traffic_control_can_actuate(requested=True, direct_long=claimed_ready, stop_assist_replay_passed=True)


def test_gap_report_is_local_and_records_blocked_state(tmp_path):
  evidence = DirectLongEvidence()
  decision = evaluate_direct_long(evidence)
  path = tmp_path / "DIRECT_LONG_GAP_REPORT.json"
  write_gap_report(path, evidence, decision)
  report = json.loads(path.read_text())
  assert report["privacy"] == "local_only_no_auto_upload"
  assert report["decision"]["state"] == "UNAVAILABLE"
  assert report["decision"]["long_can_allowed"] is False


def test_gap_report_records_bounded_local_capability_evidence(tmp_path):
  recorder = DirectLongRecorder(max_samples=2)
  for i in range(3):
    recorder.append(DirectLongSample(
      monotonic_time_s=float(i),
      ignition_on=True,
      engine_running=i > 0,
      uds_response_hex="680301" if i == 0 else None,
      faults=("Cruise_Fault",) if i == 2 else (),
    ))

  path = tmp_path / "DIRECT_LONG_GAP_REPORT.json"
  evidence = DirectLongEvidence()
  write_gap_report(path, evidence, evaluate_direct_long(evidence), recorder)
  report = json.loads(path.read_text())
  assert [sample["monotonic_time_s"] for sample in report["samples"]] == [1.0, 2.0]
  assert report["samples"][-1]["faults"] == ["Cruise_Fault"]
  assert report["privacy"] == "local_only_no_auto_upload"
