#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from openpilot.sunnypilot.selfdrive.ascent_v8.route_evidence import analyze_files


def main() -> None:
  parser = argparse.ArgumentParser(description="Extract reviewable stop candidates from Ascent V8 calibration journals")
  parser.add_argument("journals", type=Path, nargs="+")
  args = parser.parse_args()
  print(json.dumps(analyze_files(args.journals), indent=2))


if __name__ == "__main__":
  main()
