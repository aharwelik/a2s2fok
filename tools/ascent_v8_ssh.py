#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys


def resolve_prime_target(target: str) -> str:
  from openpilot.tools.lib.auth_config import get_token
  from openpilot.tools.lib.api import CommaApi

  devices = CommaApi(get_token()).get("v1/me/devices")
  by_id = {device["dongle_id"]: device.get("alias") for device in devices}
  if target in by_id:
    return target
  normalized = target.replace(" ", "").lower()
  matches = [dongle_id for dongle_id, alias in by_id.items()
             if isinstance(alias, str) and normalized in alias.replace(" ", "").lower()]
  if len(matches) != 1:
    raise SystemExit(f"expected exactly one comma device matching {target!r}, found {len(matches)}")
  return matches[0]


def main() -> None:
  parser = argparse.ArgumentParser(description="Connect to the Ascent V8 restricted maintenance endpoint")
  parser.add_argument("target", help="comma device IP/hostname, or device alias/dongle ID with --prime")
  parser.add_argument("command", choices=["status", "logs", "update", "rollback"], nargs="?", default="status")
  parser.add_argument("--key", type=Path, default=Path.home() / ".ssh/ascent_v8_maintenance")
  parser.add_argument("--prime", action="store_true", help="connect through the comma Prime SSH proxy")
  parser.add_argument("--output", type=Path, help="destination for a downloaded log bundle")
  args = parser.parse_args()
  ssh_command = [
    "ssh", "-i", str(args.key), "-o", "IdentitiesOnly=yes", "-o", "PasswordAuthentication=no",
    "-o", "KbdInteractiveAuthentication=no", "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=3",
  ]
  if args.prime:
    dongle_id = resolve_prime_target(args.target)
    proxy = f"ssh -i {shlex.quote(str(args.key))} -o IdentitiesOnly=yes -o PasswordAuthentication=no -W %h:%p %h@ssh.comma.ai"
    ssh_command += ["-o", f"ProxyCommand={proxy}", f"comma@comma-{dongle_id}"]
  else:
    ssh_command.append(f"comma@{args.target}")
  result = subprocess.run([*ssh_command, args.command], check=True, stdout=subprocess.PIPE)
  if args.command != "logs":
    sys.stdout.buffer.write(result.stdout)
    return

  payload = json.loads(result.stdout)
  if payload.get("encoding") != "base64":
    raise SystemExit("device returned an unsupported log-bundle encoding")
  contents = base64.b64decode(payload["data"], validate=True)
  if hashlib.sha256(contents).hexdigest() != payload["sha256"]:
    raise SystemExit("downloaded log-bundle checksum mismatch")
  destination = args.output or (Path.home() / "Downloads" / payload["bundle_name"])
  destination.parent.mkdir(parents=True, exist_ok=True)
  destination.write_bytes(contents)
  print(destination)


if __name__ == "__main__":
  main()
