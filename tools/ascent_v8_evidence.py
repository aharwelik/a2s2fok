#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from openpilot.sunnypilot.selfdrive.ascent_v8.route_evidence import analyze_files


def main() -> None:
  parser = argparse.ArgumentParser(description="Evaluate Ascent V8 stop responses and saved-route curves offline")
  parser.add_argument("--labels", type=Path, help="Optional private JSONL file containing video-confirmed labels")
  parser.add_argument("--qlog-root", type=Path, help="Optional saved route directory containing segment qlog.zst files")
  parser.add_argument("--output", type=Path, help="Write the JSON report to this path instead of stdout")
  parser.add_argument("journals", type=Path, nargs="+")
  args = parser.parse_args()
  qlogs = None
  if args.qlog_root is not None:
    qlogs = sorted(args.qlog_root.glob("*/qlog.zst"), key=lambda path: int(path.parent.name.rsplit("--", 1)[1]))
    if not qlogs:
      parser.error(f"no segment qlog.zst files found under {args.qlog_root}")
  report = json.dumps(analyze_files(args.journals, args.labels, qlogs), indent=2) + "\n"
  if args.output is None:
    print(report, end="")
  else:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report)


if __name__ == "__main__":
  main()
