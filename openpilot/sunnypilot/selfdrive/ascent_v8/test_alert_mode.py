import os

from opendbc.car.structs import car


TEST_ALERT_MODE_PARAM = "AscentV8TestAlertDelayEnabled"
ALPHA_NO_DM_ENV = "ALPHA_NO_DM"
EXACT_ASCENT_FINGERPRINT = "SUBARU_ASCENT_2023"

ALERT_1_TIMEOUT_S = 99 * 60
ALERT_2_TIMEOUT_S = 100 * 60
ALERT_3_TIMEOUT_S = 101 * 60


def _persistent_fingerprint(params) -> str | None:
  for key in ("CarParams", "CarParamsPersistent"):
    raw = params.get(key)
    if not raw:
      continue
    try:
      with car.CarParams.from_bytes(raw) as car_params:
        return car_params.carFingerprint
    except Exception:
      continue
  return None


def is_test_alert_mode_enabled(params, fingerprint: str | None = None) -> bool:
  if not params.get_bool(TEST_ALERT_MODE_PARAM) and os.getenv(ALPHA_NO_DM_ENV, "0") != "1":
    return False
  resolved_fingerprint = fingerprint if fingerprint is not None else _persistent_fingerprint(params)
  return resolved_fingerprint == EXACT_ASCENT_FINGERPRINT


def apply_test_alert_delay(settings, params, fingerprint: str | None = None) -> bool:
  if not is_test_alert_mode_enabled(params, fingerprint):
    return False

  settings._VISION_POLICY_ALERT_1_TIMEOUT = ALERT_1_TIMEOUT_S
  settings._VISION_POLICY_ALERT_2_TIMEOUT = ALERT_2_TIMEOUT_S
  settings._VISION_POLICY_ALERT_3_TIMEOUT = ALERT_3_TIMEOUT_S
  settings._WHEELTOUCH_POLICY_ALERT_1_TIMEOUT = ALERT_1_TIMEOUT_S
  settings._WHEELTOUCH_POLICY_ALERT_2_TIMEOUT = ALERT_2_TIMEOUT_S
  settings._WHEELTOUCH_POLICY_ALERT_3_TIMEOUT = ALERT_3_TIMEOUT_S
  return True


def neutralize_test_alert_state(driver_monitoring) -> None:
  driver_monitoring.alert_level = 0
  driver_monitoring.lockout_active = False
  driver_monitoring.alert_3_cnt = 0
  driver_monitoring.cnt_since_alert_3 = 0
  driver_monitoring.no_response_cnt = 0
