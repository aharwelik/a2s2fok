"""
Read-only 2023 Subaru Ascent combined V6 status surface.

This panel reports the selected live profile. It does not enable stop braking,
openpilot longitudinal, EyeSight disable, blinker activation, or autonomous
passing.
"""
from openpilot.sunnypilot.selfdrive.ascent_v6.status import STATUS_ROWS
from openpilot.system.ui.sunnypilot.widgets.list_view import button_item_sp
from openpilot.system.ui.widgets import Widget
from openpilot.system.ui.widgets.scroller_tici import Scroller


class AscentV6Layout(Widget):
  def __init__(self):
    super().__init__()
    self._scroller = Scroller(self._items(), line_separator=True, spacing=0)

  @staticmethod
  def _items():
    return [
      button_item_sp(
        title=lambda name=name: name,
        button_text=lambda value=value: value,
        description=lambda name=name, value=value: f"{name}: {value}",
        enabled=False,
      )
      for name, value in STATUS_ROWS
    ]

  def _render(self, rect):
    self._scroller.render(rect)

  def show_event(self):
    self._scroller.show_event()
