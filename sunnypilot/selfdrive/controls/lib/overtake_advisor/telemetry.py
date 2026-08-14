from __future__ import annotations

from dataclasses import asdict

from openpilot.sunnypilot.selfdrive.controls.lib.overtake_advisor.advisor import OvertakeRecommendation


def shadow_status(recommendation: OvertakeRecommendation) -> dict:
  data = asdict(recommendation)
  data["state"] = recommendation.state.name
  return data

