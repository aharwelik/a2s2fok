#!/usr/bin/env python3
import time

from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog
from openpilot.sunnypilot.system.ascent_maintenance.policy import install_ssh_params


REFRESH_INTERVAL_S = 30


def main() -> None:
  params = Params()
  while True:
    try:
      install_ssh_params(params)
    except Exception:
      cloudlog.exception("failed to enforce Ascent V8 restricted SSH policy")
    time.sleep(REFRESH_INTERVAL_S)


if __name__ == "__main__":
  main()
