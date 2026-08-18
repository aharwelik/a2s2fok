#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess
import time


def resolve_dongle_id(target: str) -> str:
  if re.fullmatch(r"[0-9a-fA-F]{16}", target):
    return target.lower()
  from openpilot.tools.lib.auth_config import get_token
  from openpilot.tools.lib.api import CommaApi

  devices = CommaApi(get_token()).get("v1/me/devices")
  normalized = target.replace(" ", "").lower()
  matches = [device["dongle_id"] for device in devices if isinstance(device.get("alias"), str) and
             normalized in device["alias"].replace(" ", "").lower()]
  if len(matches) != 1:
    raise SystemExit(f"expected exactly one comma device matching {target!r}, found {len(matches)}")
  return matches[0]


def build_ssh_command(host: str, key: Path, session: str, *, prime: bool) -> list[str]:
  command = [
    "ssh", "-tt", "-i", str(key),
    "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "PasswordAuthentication=no",
    "-o", "KbdInteractiveAuthentication=no", "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=2",
    "-o", "ConnectTimeout=5", "-o", "ConnectionAttempts=1", "-o", "StrictHostKeyChecking=accept-new",
    "-o", "ForwardAgent=yes",
  ]
  if prime:
    proxy = (f"ssh -i {shlex.quote(str(key))} -o IdentitiesOnly=yes -o BatchMode=yes " +
             "-o ConnectTimeout=5 -W %h:%p %h@ssh.comma.ai")
    command += ["-o", f"ProxyCommand={proxy}"]
  command += [f"comma@{host}", f"tmux new-session -A -s {shlex.quote(session)} -c /data/openpilot"]
  return command


def main() -> None:
  parser = argparse.ArgumentParser(description="Keep Anthony's MacBook attached to one persistent comma tmux session")
  parser.add_argument("target", help="16-character dongle ID, or comma device alias when authenticated")
  parser.add_argument("--local-ip", help="comma IP on the iPhone hotspot; tried before Prime")
  parser.add_argument("--key", type=Path, default=Path.home() / ".ssh/ascent_v8_operator")
  parser.add_argument("--session", default="ascent-v8-live")
  parser.add_argument("--no-prime", action="store_true", help="use only the local hotspot address")
  args = parser.parse_args()

  if not args.key.is_file():
    raise SystemExit(f"operator key not found: {args.key}")
  routes: list[tuple[str, list[str]]] = []
  if args.local_ip:
    routes.append((f"local {args.local_ip}", build_ssh_command(args.local_ip, args.key, args.session, prime=False)))
  if not args.no_prime:
    dongle_id = resolve_dongle_id(args.target)
    routes.append(("comma Prime", build_ssh_command(f"comma-{dongle_id}", args.key, args.session, prime=True)))
  if not routes:
    parser.error("provide --local-ip or leave Prime enabled")

  caffeinate = subprocess.Popen(["caffeinate", "-dimsu", "-w", str(os.getpid())])
  try:
    while True:
      for label, command in routes:
        print(f"connecting through {label}; Control-C stops the reconnect loop", flush=True)
        subprocess.run(command, check=False)
        time.sleep(2)
  except KeyboardInterrupt:
    print("\nlive connection stopped")
  finally:
    caffeinate.terminate()


if __name__ == "__main__":
  main()
