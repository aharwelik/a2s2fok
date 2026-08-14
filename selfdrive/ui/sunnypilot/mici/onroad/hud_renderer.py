"""
Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.

This file is part of sunnypilot and is licensed under the MIT License.
See the LICENSE.md file in the root directory for more details.
"""
import pyray as rl

from openpilot.selfdrive.ui.mici.onroad.hud_renderer import HudRenderer
from openpilot.selfdrive.ui.sunnypilot.onroad.blind_spot_indicators import BlindSpotIndicators
from openpilot.sunnypilot.selfdrive.ascent_v7.status import DEVELOPMENT_LABEL
from openpilot.system.ui.lib.application import FontWeight, gui_app
from openpilot.system.ui.lib.text_measure import measure_text_cached


class HudRendererSP(HudRenderer):
  def __init__(self):
    super().__init__()
    self.blind_spot_indicators = BlindSpotIndicators()
    self._ascent_v6_font = gui_app.font(FontWeight.BOLD)

  def _update_state(self) -> None:
    super()._update_state()
    self.blind_spot_indicators.update()

  def _render(self, rect: rl.Rectangle) -> None:
    super()._render(rect)
    self.blind_spot_indicators.render(rect)
    self._render_ascent_v6_banner(rect)

  def _has_blind_spot_detected(self) -> bool:

    return self.blind_spot_indicators.detected

  def _render_ascent_v6_banner(self, rect: rl.Rectangle) -> None:
    font_size = 28
    text_size = measure_text_cached(self._ascent_v6_font, DEVELOPMENT_LABEL, font_size)
    pad_x = 18
    pad_y = 8
    banner = rl.Rectangle(
      rect.x + (rect.width - text_size.x) / 2 - pad_x,
      rect.y + rect.height - 72,
      text_size.x + 2 * pad_x,
      text_size.y + 2 * pad_y,
    )
    rl.draw_rectangle_rounded(banner, 0.35, 8, rl.Color(0, 0, 0, 150))
    rl.draw_text_ex(
      self._ascent_v6_font,
      DEVELOPMENT_LABEL,
      rl.Vector2(banner.x + pad_x, banner.y + pad_y),
      font_size,
      0,
      rl.Color(255, 255, 255, 225),
    )
