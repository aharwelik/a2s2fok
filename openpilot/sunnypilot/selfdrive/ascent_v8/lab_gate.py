from dataclasses import dataclass
from enum import StrEnum


class GateState(StrEnum):
  DISABLED = "DISABLED"
  READY = "READY"
  BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class LabInputs:
  master_enabled: bool
  exact_vehicle: bool
  build_hash_ok: bool
  geofence_ok: bool
  gps_fresh: bool
  laptop_heartbeat_fresh: bool
  estop_healthy: bool
  panda_state_valid: bool
  vehicle_fault_free: bool
  model_fresh: bool
  occupancy_known: bool
  speed_within_phase: bool
  update_in_progress: bool = False


@dataclass(frozen=True)
class LabDecision:
  state: GateState
  reasons: tuple[str, ...]


class LabGateEvaluator:
  def evaluate(self, inputs: LabInputs) -> LabDecision:
    if not inputs.master_enabled:
      return LabDecision(GateState.DISABLED, ("master_disabled",))
    checks = {
      "wrong_vehicle": inputs.exact_vehicle,
      "wrong_build": inputs.build_hash_ok,
      "outside_geofence": inputs.geofence_ok,
      "gps_stale": inputs.gps_fresh,
      "laptop_heartbeat_lost": inputs.laptop_heartbeat_fresh,
      "estop_unhealthy": inputs.estop_healthy,
      "panda_invalid": inputs.panda_state_valid,
      "vehicle_fault": inputs.vehicle_fault_free,
      "model_stale": inputs.model_fresh,
      "occupancy_unknown": inputs.occupancy_known,
      "phase_speed_exceeded": inputs.speed_within_phase,
      "update_in_progress": not inputs.update_in_progress,
    }
    reasons = tuple(name for name, passed in checks.items() if not passed)
    return LabDecision(GateState.BLOCKED if reasons else GateState.READY, reasons)
