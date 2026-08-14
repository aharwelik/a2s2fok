from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any


DIRECT_LONG_ALPHA_DEFAULT = False
TRAFFIC_CONTROL_ALPHA_DEFAULT = False

# Physical direct-long remains compiled out until current Ascent message
# templates, Panda longitudinal safety, replay, NOBOARD, and exact-vehicle
# parked gates all pass. Updating this constant alone is not an authorization;
# the evidence evaluator below must also pass every gate.
PANDA_LONG_RUNTIME_COMPILED = False
TRAFFIC_CONTROL_RUNTIME_COMPILED = False


class DirectLongState(str, Enum):
  UNAVAILABLE = "UNAVAILABLE"
  IGNITION_ONLY_WAIT = "IGNITION_ONLY_WAIT"
  EYESIGHT_DISABLE_ATTEMPT = "EYESIGHT_DISABLE_ATTEMPT"
  EYESIGHT_DISABLED_PRE_ENGINE = "EYESIGHT_DISABLED_PRE_ENGINE"
  CRANK_KEEPALIVE = "CRANK_KEEPALIVE"
  EYESIGHT_DISABLED_ENGINE_RUNNING = "EYESIGHT_DISABLED_ENGINE_RUNNING"
  REPLACEMENT_MESSAGES_READY = "REPLACEMENT_MESSAGES_READY"
  PANDA_LONG_READY = "PANDA_LONG_READY"
  CRUISE_STATE_READY = "CRUISE_STATE_READY"
  SHADOW_LONG_READY = "SHADOW_LONG_READY"
  LOW_SPEED_LONG_READY = "LOW_SPEED_LONG_READY"
  ALPHA_LONG_ACTIVE = "ALPHA_LONG_ACTIVE"
  FAILED_SAFE = "FAILED_SAFE"


@dataclass(frozen=True)
class DirectLongEvidence:
  exact_ascent_2023: bool = False
  explicit_alpha_request: bool = False
  ignition_on: bool = False
  engine_running: bool = False
  disable_attempted: bool = False
  disable_response_ok: bool = False
  tester_present_during_crank: bool = False
  disable_survived_crank: bool = False
  replacement_message_tests_passed: bool = False
  panda_long_tests_passed: bool = False
  cruise_state_tests_passed: bool = False
  shadow_replay_passed: bool = False
  no_relay_malfunction: bool = False
  no_unexpected_vehicle_fault: bool = False
  parked_vehicle_gate_passed: bool = False
  low_speed_closed_course_passed: bool = False


@dataclass(frozen=True)
class DirectLongDecision:
  state: DirectLongState
  long_can_allowed: bool
  reason: str


@dataclass(frozen=True)
class DirectLongSample:
  """One local-only observation from a future exact-vehicle capability run."""
  monotonic_time_s: float
  ignition_on: bool
  engine_running: bool
  uds_response_hex: str | None = None
  tester_present_age_s: float | None = None
  eyesight_disabled_post_crank: bool = False
  relay_malfunction: bool = False
  cruise_fault: bool = False
  controls_allowed: bool = False
  openpilot_longitudinal_control: bool = False
  requested_accel: float = 0.0
  actual_accel: float = 0.0
  brake_pressed: bool = False
  gas_pressed: bool = False
  standstill: bool = False
  lead_status: str = "UNKNOWN"
  stop_source: str = "NONE"
  stop_target_m: float | None = None
  replacement_message_health: str = "NOT_TESTED"
  panda_safety_state: str = "BLOCKED"
  faults: tuple[str, ...] = ()


class DirectLongRecorder:
  """Bounded in-memory recorder; it never transmits or uploads data."""
  def __init__(self, max_samples: int = 2000):
    if max_samples < 1:
      raise ValueError("max_samples must be positive")
    self.max_samples = max_samples
    self._samples: list[DirectLongSample] = []

  def append(self, sample: DirectLongSample) -> None:
    self._samples.append(sample)
    del self._samples[:-self.max_samples]

  def to_json(self) -> list[dict[str, Any]]:
    return [asdict(sample) for sample in self._samples]


def evaluate_direct_long(evidence: DirectLongEvidence) -> DirectLongDecision:
  """Evaluate evidence without performing diagnostics or vehicle actuation."""
  if not evidence.explicit_alpha_request:
    return DirectLongDecision(DirectLongState.UNAVAILABLE, False, "alpha_default_off")
  if not evidence.exact_ascent_2023:
    return DirectLongDecision(DirectLongState.FAILED_SAFE, False, "exact_vehicle_identity_required")
  if not evidence.ignition_on:
    return DirectLongDecision(DirectLongState.IGNITION_ONLY_WAIT, False, "ignition_required")
  if evidence.engine_running and not evidence.disable_survived_crank:
    return DirectLongDecision(DirectLongState.FAILED_SAFE, False, "no_post_crank_disable_proof")
  if not evidence.disable_attempted:
    return DirectLongDecision(DirectLongState.EYESIGHT_DISABLE_ATTEMPT, False, "diagnostic_attempt_not_recorded")
  if not evidence.disable_response_ok:
    return DirectLongDecision(DirectLongState.FAILED_SAFE, False, "disable_response_failed")
  if not evidence.engine_running:
    return DirectLongDecision(DirectLongState.EYESIGHT_DISABLED_PRE_ENGINE, False, "awaiting_crank_proof")
  if not evidence.tester_present_during_crank:
    return DirectLongDecision(DirectLongState.FAILED_SAFE, False, "crank_keepalive_missing")
  if not evidence.disable_survived_crank:
    return DirectLongDecision(DirectLongState.CRANK_KEEPALIVE, False, "disable_not_proven_after_crank")
  if not evidence.replacement_message_tests_passed:
    return DirectLongDecision(DirectLongState.EYESIGHT_DISABLED_ENGINE_RUNNING, False, "replacement_messages_unproven")
  if not evidence.panda_long_tests_passed or not PANDA_LONG_RUNTIME_COMPILED:
    return DirectLongDecision(DirectLongState.FAILED_SAFE, False, "panda_long_runtime_blocked")
  if not evidence.cruise_state_tests_passed:
    return DirectLongDecision(DirectLongState.PANDA_LONG_READY, False, "cruise_state_unproven")
  if not evidence.shadow_replay_passed:
    return DirectLongDecision(DirectLongState.CRUISE_STATE_READY, False, "shadow_replay_unproven")
  if not evidence.no_relay_malfunction or not evidence.no_unexpected_vehicle_fault:
    return DirectLongDecision(DirectLongState.FAILED_SAFE, False, "vehicle_fault_gate_failed")
  if not evidence.parked_vehicle_gate_passed:
    return DirectLongDecision(DirectLongState.SHADOW_LONG_READY, False, "parked_vehicle_gate_required")
  if not evidence.low_speed_closed_course_passed:
    return DirectLongDecision(DirectLongState.LOW_SPEED_LONG_READY, False, "low_speed_validation_required")
  return DirectLongDecision(DirectLongState.ALPHA_LONG_ACTIVE, True, "all_gates_passed")


def traffic_control_can_actuate(*, requested: bool, direct_long: DirectLongDecision,
                                stop_assist_replay_passed: bool) -> bool:
  return bool(requested and TRAFFIC_CONTROL_RUNTIME_COMPILED and stop_assist_replay_passed and
              direct_long.state == DirectLongState.ALPHA_LONG_ACTIVE and direct_long.long_can_allowed)


def write_gap_report(path: Path, evidence: DirectLongEvidence, decision: DirectLongDecision,
                     recorder: DirectLongRecorder | None = None) -> None:
  report = {
    "schema_version": 1,
    "default_enabled": DIRECT_LONG_ALPHA_DEFAULT,
    "runtime_compiled": PANDA_LONG_RUNTIME_COMPILED,
    "evidence": asdict(evidence),
    "decision": {"state": decision.state.value, "long_can_allowed": decision.long_can_allowed, "reason": decision.reason},
    "samples": recorder.to_json() if recorder is not None else [],
    "privacy": "local_only_no_auto_upload",
  }
  path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
