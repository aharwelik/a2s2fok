from __future__ import annotations

from dataclasses import asdict

from openpilot.sunnypilot.selfdrive.ascent_v6.status import model_stop_label
from openpilot.sunnypilot.selfdrive.controls.lib.stop_obstacle.estimator import StopTarget


def shadow_status(target: StopTarget) -> dict:
  data = asdict(target)
  data["source"] = target.source.name
  data["rejection_reason"] = target.rejection_reason.name
  data["label"] = model_stop_label(target.distance_m) if target.valid else ""
  return data

