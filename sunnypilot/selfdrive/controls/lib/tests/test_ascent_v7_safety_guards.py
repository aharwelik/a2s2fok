from types import SimpleNamespace

import pytest

from opendbc.safety import ALTERNATIVE_EXPERIENCE
from openpilot.selfdrive.controls.controlsd import BOOT_CANCEL_GRACE_S, cruise_cancel_allowed
from openpilot.sunnypilot.selfdrive.controls.controlsd_ext import ControlsExt
from openpilot.sunnypilot.selfdrive.controls.lib.longitudinal_planner import clamp_speed_cap_accel


class _BlinkerPause:
  @staticmethod
  def update(_car_state):
    return False


def _controls_ext():
  return SimpleNamespace(blinker_pause_lateral=_BlinkerPause())


def _sm(*, mads_active=True, cruise_enabled=False, panda_states=()):
  return {
    'carState': SimpleNamespace(cruiseState=SimpleNamespace(enabled=cruise_enabled)),
    'selfdriveState': SimpleNamespace(active=False),
    'selfdriveStateSP': SimpleNamespace(mads=SimpleNamespace(available=True, active=mads_active)),
    'pandaStates': list(panda_states),
  }


def _panda(alternative_experience):
  return SimpleNamespace(alternativeExperience=alternative_experience)


def test_independent_mads_fails_closed_without_panda_state():
  assert not ControlsExt.get_lat_active(_controls_ext(), _sm())


def test_independent_mads_fails_closed_without_enable_mads_bit():
  assert not ControlsExt.get_lat_active(_controls_ext(), _sm(panda_states=[_panda(0)]))


def test_independent_mads_requires_enable_mads_bit():
  panda = _panda(ALTERNATIVE_EXPERIENCE.ENABLE_MADS)
  assert ControlsExt.get_lat_active(_controls_ext(), _sm(panda_states=[panda]))


def test_stock_acc_set_path_does_not_require_independent_mads_bit():
  assert ControlsExt.get_lat_active(_controls_ext(), _sm(cruise_enabled=True))


@pytest.mark.parametrize(
  "engageable,seconds,expected",
  [
    (False, 0.0, False),
    (False, BOOT_CANCEL_GRACE_S, True),
    (False, BOOT_CANCEL_GRACE_S + 0.1, True),
    (True, 0.0, True),
  ],
)
def test_boot_cancel_guard_is_bounded(engageable, seconds, expected):
  frame = round(seconds / 0.01)
  assert cruise_cancel_allowed(engageable, frame) is expected


@pytest.mark.parametrize(
  "candidate,actual,expected",
  [
    (1.0, -2.0, -2.0),
    (-3.0, -2.0, -3.0),
    (-1.0, 0.0, -1.0),
    (0.0, 0.0, 0.0),
  ],
)
def test_speed_caps_never_inject_more_positive_acceleration(candidate, actual, expected):
  assert clamp_speed_cap_accel(candidate, actual) == expected
