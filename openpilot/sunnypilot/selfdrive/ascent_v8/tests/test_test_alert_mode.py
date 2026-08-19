from openpilot.cereal import log
from opendbc.car.structs import car
from openpilot.common.realtime import DT_DMON
from openpilot.selfdrive.monitoring.policy import DRIVER_MONITOR_SETTINGS, DriverMonitoring
from openpilot.sunnypilot.selfdrive.ascent_v8.test_alert_mode import (
  ALERT_1_TIMEOUT_S,
  ALERT_2_TIMEOUT_S,
  ALERT_3_TIMEOUT_S,
  ALPHA_NO_DM_ENV,
  TEST_ALERT_MODE_PARAM,
  apply_test_alert_delay,
  is_test_alert_mode_enabled,
  neutralize_test_alert_state,
)


class ParamsStub:
  def __init__(self, *, enabled: bool, fingerprint: str | None = None):
    self.enabled = enabled
    self.car_params = None
    if fingerprint is not None:
      cp = car.CarParams.new_message()
      cp.carFingerprint = fingerprint
      self.car_params = cp.to_bytes()

  def get_bool(self, key: str) -> bool:
    return self.enabled if key == TEST_ALERT_MODE_PARAM else False

  def get(self, key: str):
    return self.car_params if key in ("CarParamsPersistent", "CarParams") else None


def _distracted_driver_state():
  state = log.DriverStateV2.new_message()
  state.leftDriverData.faceOrientation = [0.0, 0.0, 0.0]
  state.leftDriverData.facePosition = [0.0, 0.0]
  state.leftDriverData.faceProb = 1.0
  state.leftDriverData.leftEyeProb = 1.0
  state.leftDriverData.rightEyeProb = 1.0
  state.leftDriverData.leftBlinkProb = 1.0
  state.leftDriverData.rightBlinkProb = 1.0
  state.leftDriverData.faceOrientationStd = [0.0, 0.0, 0.0]
  state.leftDriverData.facePositionStd = [0.0, 0.0]
  state.leftDriverData.phoneProb = 0.0
  return state


def test_mode_is_default_off_and_exact_ascent_only():
  assert not is_test_alert_mode_enabled(ParamsStub(enabled=False, fingerprint="SUBARU_ASCENT_2023"))
  assert not is_test_alert_mode_enabled(ParamsStub(enabled=True, fingerprint="SUBARU_OUTBACK_2023"))
  assert is_test_alert_mode_enabled(ParamsStub(enabled=True, fingerprint="SUBARU_ASCENT_2023"))


def test_explicit_fingerprint_path_is_also_exact_ascent_only():
  params = ParamsStub(enabled=True)
  assert is_test_alert_mode_enabled(params, "SUBARU_ASCENT_2023")
  assert not is_test_alert_mode_enabled(params, "SUBARU_OUTBACK_2023")


def test_alpha_no_dm_environment_override_is_exact_ascent_only(monkeypatch):
  monkeypatch.setenv(ALPHA_NO_DM_ENV, "1")
  assert is_test_alert_mode_enabled(ParamsStub(enabled=False, fingerprint="SUBARU_ASCENT_2023"))
  assert not is_test_alert_mode_enabled(ParamsStub(enabled=False, fingerprint="SUBARU_OUTBACK_2023"))

  settings = DRIVER_MONITOR_SETTINGS()
  assert apply_test_alert_delay(settings, ParamsStub(enabled=False, fingerprint="SUBARU_ASCENT_2023"))
  assert settings._VISION_POLICY_ALERT_1_TIMEOUT == 99 * 60

  monkeypatch.setenv(ALPHA_NO_DM_ENV, "0")
  assert not is_test_alert_mode_enabled(ParamsStub(enabled=False, fingerprint="SUBARU_ASCENT_2023"))


def test_delay_changes_both_monitoring_policies_to_99_minutes():
  settings = DRIVER_MONITOR_SETTINGS()
  assert apply_test_alert_delay(settings, ParamsStub(enabled=True, fingerprint="SUBARU_ASCENT_2023"))
  assert settings._VISION_POLICY_ALERT_1_TIMEOUT == ALERT_1_TIMEOUT_S == 99 * 60
  assert settings._VISION_POLICY_ALERT_2_TIMEOUT == ALERT_2_TIMEOUT_S
  assert settings._VISION_POLICY_ALERT_3_TIMEOUT == ALERT_3_TIMEOUT_S
  assert settings._WHEELTOUCH_POLICY_ALERT_1_TIMEOUT == ALERT_1_TIMEOUT_S
  assert settings._WHEELTOUCH_POLICY_ALERT_2_TIMEOUT == ALERT_2_TIMEOUT_S
  assert settings._WHEELTOUCH_POLICY_ALERT_3_TIMEOUT == ALERT_3_TIMEOUT_S


def test_wrong_car_keeps_stock_timeouts():
  settings = DRIVER_MONITOR_SETTINGS()
  stock = (
    settings._VISION_POLICY_ALERT_1_TIMEOUT,
    settings._VISION_POLICY_ALERT_2_TIMEOUT,
    settings._VISION_POLICY_ALERT_3_TIMEOUT,
    settings._WHEELTOUCH_POLICY_ALERT_1_TIMEOUT,
    settings._WHEELTOUCH_POLICY_ALERT_2_TIMEOUT,
    settings._WHEELTOUCH_POLICY_ALERT_3_TIMEOUT,
  )
  assert not apply_test_alert_delay(settings, ParamsStub(enabled=True, fingerprint="SUBARU_OUTBACK_2023"))
  assert stock == (
    settings._VISION_POLICY_ALERT_1_TIMEOUT,
    settings._VISION_POLICY_ALERT_2_TIMEOUT,
    settings._VISION_POLICY_ALERT_3_TIMEOUT,
    settings._WHEELTOUCH_POLICY_ALERT_1_TIMEOUT,
    settings._WHEELTOUCH_POLICY_ALERT_2_TIMEOUT,
    settings._WHEELTOUCH_POLICY_ALERT_3_TIMEOUT,
  )


def test_no_attention_alert_during_first_two_minutes():
  settings = DRIVER_MONITOR_SETTINGS()
  apply_test_alert_delay(settings, ParamsStub(enabled=True, fingerprint="SUBARU_ASCENT_2023"))
  monitoring = DriverMonitoring(settings=settings)
  state = _distracted_driver_state()

  for _ in range(int(120 / DT_DMON)):
    monitoring._update_states(state, [0.0, 0.0, 0.0], 0.0, True, False)
    monitoring._update_events(False, True, False, 0)

  assert monitoring.alert_level == log.DriverMonitoringState.AlertLevel.none
  assert not monitoring.lockout_active


def test_alert_boundaries_start_at_99_minutes():
  settings = DRIVER_MONITOR_SETTINGS()
  apply_test_alert_delay(settings, ParamsStub(enabled=True, fingerprint="SUBARU_ASCENT_2023"))
  monitoring = DriverMonitoring(settings=settings)
  monitoring.face_detected = True
  monitoring.pose.low_std = True
  monitoring.driver_distracted = True
  monitoring.driver_distraction_filter.x = 1.0
  first_seen = {}

  for frame in range(int((ALERT_3_TIMEOUT_S + 1) / DT_DMON)):
    monitoring._update_events(False, True, False, 0)
    first_seen.setdefault(monitoring.alert_level, (frame + 1) * DT_DMON)

  assert first_seen[log.DriverMonitoringState.AlertLevel.one] == ALERT_1_TIMEOUT_S + DT_DMON
  assert first_seen[log.DriverMonitoringState.AlertLevel.two] == ALERT_2_TIMEOUT_S + DT_DMON
  assert first_seen[log.DriverMonitoringState.AlertLevel.three] == ALERT_3_TIMEOUT_S + DT_DMON


def test_telemetry_only_backstop_neutralizes_alert_and_lockout_state():
  monitoring = DriverMonitoring()
  monitoring.alert_level = log.DriverMonitoringState.AlertLevel.three
  monitoring.lockout_active = True
  monitoring.alert_3_cnt = 2
  monitoring.cnt_since_alert_3 = 100
  monitoring.no_response_cnt = 1

  neutralize_test_alert_state(monitoring)

  assert monitoring.alert_level == log.DriverMonitoringState.AlertLevel.none
  assert not monitoring.lockout_active
  assert monitoring.alert_3_cnt == 0
  assert monitoring.cnt_since_alert_3 == 0
  assert monitoring.no_response_cnt == 0
  state = monitoring.get_state_packet().driverMonitoringState
  assert not state.lockout
  assert not state.noResponseForceDecel
