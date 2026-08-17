from types import SimpleNamespace
import threading

import numpy as np
import pytest

from openpilot.sunnypilot.modeld_v2.modeld import (
  NonFiniteModelOutput,
  load_model_pair,
  switch_to_native_model,
  validate_big_model_outputs,
)


class FakeParams:
  def __init__(self):
    self.values = {}

  def put_bool(self, key, value):
    self.values[key] = bool(value)

  def remove(self, key):
    self.values.pop(key, None)


def fake_model(usbgpu: bool):
  return SimpleNamespace(usbgpu=usbgpu, lat_delay=0.2, PLANPLUS_CONTROL=1.0)


def test_preloads_native_fallback_when_chestnut_loads():
  calls = []

  def factory(*, cam_w, cam_h, usbgpu):
    calls.append((cam_w, cam_h, usbgpu))
    return fake_model(usbgpu)

  params = FakeParams()
  model, small_model = load_model_pair(1928, 1208, True, params, factory, timeout_s=1.0)

  assert model.usbgpu
  assert small_model is not None and not small_model.usbgpu
  assert calls == [(1928, 1208, True), (1928, 1208, False)]
  assert params.values == {"UsbGpuLoading": False, "UsbGpuActive": True}


def test_chestnut_load_failure_starts_native_model():
  def factory(*, cam_w, cam_h, usbgpu):
    if usbgpu:
      raise RuntimeError("USB unavailable")
    return fake_model(False)

  params = FakeParams()
  model, small_model = load_model_pair(1928, 1208, True, params, factory, timeout_s=1.0)

  assert model is small_model
  assert not model.usbgpu
  assert params.values == {"UsbGpuLoading": False, "UsbGpuActive": False}


def test_late_chestnut_load_cannot_replace_selected_native_model():
  big_started = threading.Event()
  release_big = threading.Event()

  def factory(*, cam_w, cam_h, usbgpu):
    if usbgpu:
      big_started.set()
      release_big.wait(1.0)
    return fake_model(usbgpu)

  params = FakeParams()
  model, small_model = load_model_pair(1928, 1208, True, params, factory, timeout_s=0.001)
  release_big.set()

  assert big_started.is_set()
  assert model is small_model
  assert not model.usbgpu
  assert params.values["UsbGpuActive"] is False


def test_loading_flag_clears_if_native_model_also_fails():
  def factory(*, cam_w, cam_h, usbgpu):
    raise RuntimeError("no model")

  params = FakeParams()
  with pytest.raises(RuntimeError, match="no model"):
    load_model_pair(1928, 1208, False, params, factory, timeout_s=0.0)
  assert params.values["UsbGpuLoading"] is False


def test_runtime_switch_preserves_live_tuning():
  big_model = fake_model(True)
  big_model.lat_delay = 0.47
  big_model.PLANPLUS_CONTROL = 1.25
  small_model = fake_model(False)
  params = FakeParams()

  selected = switch_to_native_model(big_model, small_model, params)

  assert selected is small_model
  assert selected.lat_delay == 0.47
  assert selected.PLANPLUS_CONTROL == 1.25
  assert params.values["UsbGpuActive"] is False


def test_nonfinite_big_output_triggers_fallback_error():
  validate_big_model_outputs({"plan": np.zeros((1, 2), dtype=np.float32)})
  with pytest.raises(NonFiniteModelOutput, match="plan"):
    validate_big_model_outputs({"plan": np.array([[0.0, np.nan]], dtype=np.float32)})
