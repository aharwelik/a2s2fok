#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile
import tempfile
from typing import TYPE_CHECKING

from openpilot.sunnypilot.system.ascent_maintenance.policy import (
  EXPECTED_BRANCH,
  EXPECTED_REMOTE,
  LEGACY_REMOTE,
  RELEASE_PUBLIC_KEY,
  RELEASE_SIGNATURE_NAMESPACE,
  RELEASE_SIGNER_IDENTITY,
  VehicleGateInputs,
  evaluate_mutation_gate,
  install_ssh_params,
)

if TYPE_CHECKING:
  from openpilot.common.params import Params


REPO = Path("/data/openpilot")
RELEASE_MANIFEST = "release/ascent_v8/manifest.json"
RELEASE_SIGNATURE = "release/ascent_v8/manifest.json.sig"
SAFE_SSH_COMMANDS = {"status", "logs", "update", "rollback"}
SAFE_PARAM_NAMES = (
  "Version", "GitCommit", "GitBranch", "LastManagerExitReason", "CurrentRoute",
  "IsOffroad", "IsEngaged", "ControlsReady", "PandaHeartbeatLost", "LastUpdateException",
  "AscentV8ShadowStatus", "UsbGpuActive", "UsbGpuLoading",
  "AscentV8CalibrationStatus",
)


class MaintenanceError(RuntimeError):
  pass


def run(command: list[str], cwd: Path = REPO, timeout: int = 120, input_data: bytes | None = None) -> subprocess.CompletedProcess:
  return subprocess.run(command, cwd=cwd, input=input_data, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        timeout=timeout, check=True)


def git(*args: str, cwd: Path = REPO, timeout: int = 120) -> str:
  return run(["git", *args], cwd=cwd, timeout=timeout).stdout.decode(errors="replace").strip()


def gate(params: Params) -> dict:
  inputs = VehicleGateInputs(
    is_offroad=params.get_bool("IsOffroad"),
    is_engaged=params.get_bool("IsEngaged"),
    controls_ready=params.get_bool("ControlsReady"),
  )
  decision = evaluate_mutation_gate(inputs)
  return {"allowed": decision.allowed, "reasons": list(decision.reasons), "inputs": inputs.__dict__}


def require_mutation_gate(params: Params) -> None:
  decision = gate(params)
  if not decision["allowed"]:
    raise MaintenanceError(f"parked/offroad gate rejected operation: {','.join(decision['reasons'])}")


def status(params: Params, repo: Path = REPO) -> dict:
  install_ssh_params(params)
  shadow = params.get("AscentV8ShadowStatus")
  calibration = params.get("AscentV8CalibrationStatus")
  usbgpu_loading = params.get_bool("UsbGpuLoading")
  usbgpu_active = params.get("UsbGpuActive")
  model_mode = "loading" if usbgpu_loading else "Chestnut" if usbgpu_active is True else "native" if usbgpu_active is False else "unknown"
  result = {
    "maintenance_transport": "restricted-maintenance-plus-macbook-operator",
    "gate": gate(params),
    "repo": str(repo),
    "model_mode": model_mode,
    "shadow": shadow,
    "calibration": calibration,
  }
  if repo.is_dir() and (repo / ".git").exists():
    result.update({
      "branch": git("branch", "--show-current", cwd=repo),
      "commit": git("rev-parse", "HEAD", cwd=repo),
      "dirty": bool(git("status", "--porcelain", cwd=repo)),
      "opendbc": git("-C", "opendbc_repo", "rev-parse", "HEAD", cwd=repo),
    })
  return result


def _capture(command: list[str], cwd: Path, timeout: int = 20) -> str:
  try:
    return run(command, cwd=cwd, timeout=timeout).stdout.decode(errors="replace")
  except Exception as error:
    return f"COMMAND_FAILED: {shlex.join(command)}: {error}\n"


def collect_logs(params: Params, repo: Path = REPO, destination: Path = Path("/data/ascent_maintenance/bundles"),
                 calibration_root: Path = Path("/data/ascent_maintenance/calibration")) -> Path:
  require_mutation_gate(params)
  timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
  destination.mkdir(parents=True, exist_ok=True)
  bundle = destination / f"ascent-v8-diagnostics-{timestamp}.tar.gz"

  with tempfile.TemporaryDirectory(prefix="ascent-v8-diagnostics-") as temp_dir_name:
    temp_dir = Path(temp_dir_name)
    safe_params = {name: params.get(name) for name in SAFE_PARAM_NAMES}
    for name, value in list(safe_params.items()):
      if isinstance(value, bytes):
        safe_params[name] = value.decode(errors="replace")
    (temp_dir / "params.json").write_text(json.dumps(safe_params, indent=2, sort_keys=True))
    (temp_dir / "status.json").write_text(json.dumps(status(params, repo), indent=2, sort_keys=True))
    commands = {
      "uname.txt": ["uname", "-a"],
      "git-status.txt": ["git", "status", "--short", "--branch"],
      "submodules.txt": ["git", "submodule", "status", "--recursive"],
      "manager-processes.txt": ["pgrep", "-af", "manager|controlsd|pandad|loggerd|athena|ascent_maintenance"],
      "journal.txt": ["journalctl", "-b", "--no-pager", "-n", "2500"],
      "disk.txt": ["df", "-h"],
      "network.txt": ["ip", "address", "show"],
    }
    for filename, command in commands.items():
      (temp_dir / filename).write_text(_capture(command, repo))
    calibration_dir = temp_dir / "calibration"
    calibration_dir.mkdir()
    for path in sorted(calibration_root.glob("*.jsonl"), key=lambda item: item.stat().st_mtime)[-8:]:
      shutil.copy2(path, calibration_dir / path.name)
    with tarfile.open(bundle, "w:gz") as archive:
      for path in sorted(temp_dir.iterdir()):
        archive.add(path, arcname=path.name)
  return bundle


def validate_release_manifest(manifest: dict) -> None:
  required = {"schema", "branch", "root_source_sha", "opendbc_sha", "created_utc"}
  if set(manifest) != required:
    raise MaintenanceError("release manifest fields do not match the V8 schema")
  if manifest["schema"] != 1 or manifest["branch"] != EXPECTED_BRANCH:
    raise MaintenanceError("release manifest targets the wrong schema or branch")
  for name in ("root_source_sha", "opendbc_sha"):
    value = manifest[name]
    if not isinstance(value, str) or len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
      raise MaintenanceError(f"invalid {name}")
  try:
    created_utc = datetime.datetime.fromisoformat(manifest["created_utc"].replace("Z", "+00:00"))
  except (AttributeError, TypeError, ValueError) as error:
    raise MaintenanceError("invalid created_utc") from error
  if created_utc.tzinfo != datetime.UTC:
    raise MaintenanceError("created_utc must be UTC")


def verify_release_signature(manifest_bytes: bytes, signature_bytes: bytes) -> None:
  with tempfile.TemporaryDirectory(prefix="ascent-v8-signature-") as temp_dir_name:
    temp_dir = Path(temp_dir_name)
    allowed_signers = temp_dir / "allowed_signers"
    signature = temp_dir / "manifest.sig"
    allowed_signers.write_text(f"{RELEASE_SIGNER_IDENTITY} {RELEASE_PUBLIC_KEY}\n")
    signature.write_bytes(signature_bytes)
    run(["ssh-keygen", "-Y", "verify", "-f", str(allowed_signers), "-I", RELEASE_SIGNER_IDENTITY,
         "-n", RELEASE_SIGNATURE_NAMESPACE, "-s", str(signature)], cwd=temp_dir, input_data=manifest_bytes)


def verify_fetched_release(repo: Path, remote_head: str) -> tuple[dict, str]:
  manifest_bytes = run(["git", "show", f"{remote_head}:{RELEASE_MANIFEST}"], cwd=repo).stdout
  signature_bytes = run(["git", "show", f"{remote_head}:{RELEASE_SIGNATURE}"], cwd=repo).stdout
  verify_release_signature(manifest_bytes, signature_bytes)
  manifest = json.loads(manifest_bytes)
  validate_release_manifest(manifest)

  source_sha = manifest["root_source_sha"]
  if git("rev-parse", f"{remote_head}^", cwd=repo) != source_sha:
    raise MaintenanceError("release metadata commit is not directly based on its signed source")
  changed = set(git("diff", "--name-only", source_sha, remote_head, cwd=repo).splitlines())
  if not changed or not changed.issubset({RELEASE_MANIFEST, RELEASE_SIGNATURE}):
    raise MaintenanceError("unsigned files are present in the release metadata commit")
  opendbc_sha = git("ls-tree", source_sha, "opendbc_repo", cwd=repo).split()[2]
  if opendbc_sha != manifest["opendbc_sha"]:
    raise MaintenanceError("signed OpenDBC SHA does not match the root source lock")
  return manifest, source_sha


def ensure_expected_remote(repo: Path) -> None:
  remote = git("remote", "get-url", "origin", cwd=repo)
  if remote == LEGACY_REMOTE:
    git("remote", "set-url", "origin", EXPECTED_REMOTE, cwd=repo)
  elif remote != EXPECTED_REMOTE:
    raise MaintenanceError("origin URL is not the approved public repository")


def update(params: Params, repo: Path = REPO) -> dict:
  require_mutation_gate(params)
  if git("status", "--porcelain", cwd=repo):
    raise MaintenanceError("working tree is dirty")
  ensure_expected_remote(repo)

  previous = git("rev-parse", "HEAD", cwd=repo)
  git("fetch", "--recurse-submodules=no", "origin", EXPECTED_BRANCH, cwd=repo, timeout=300)
  remote_head = git("rev-parse", "FETCH_HEAD", cwd=repo)
  manifest, source_sha = verify_fetched_release(repo, remote_head)
  rollback_ref = f"rollback/ascent-v8-{datetime.datetime.now(datetime.UTC).strftime('%Y%m%dT%H%M%SZ')}"
  git("branch", rollback_ref, previous, cwd=repo)

  try:
    git("switch", "-C", EXPECTED_BRANCH, remote_head, cwd=repo)
    git("submodule", "sync", "--recursive", cwd=repo)
    git("submodule", "update", "--init", "--recursive", cwd=repo, timeout=900)
    run(["python3", "scripts/ascent/audit_v8_fail_closed.py"], cwd=repo, timeout=120)
  except Exception:
    git("switch", "-C", EXPECTED_BRANCH, previous, cwd=repo)
    git("submodule", "update", "--init", "--recursive", cwd=repo, timeout=900)
    raise
  return {"updated": previous != remote_head, "previous": previous, "release_head": remote_head,
          "root_source_sha": source_sha, "opendbc_sha": manifest["opendbc_sha"], "rollback": rollback_ref}


def rollback(params: Params, repo: Path = REPO) -> dict:
  require_mutation_gate(params)
  refs = git("for-each-ref", "--sort=-creatordate", "--format=%(refname:short)", "refs/heads/rollback/ascent-v8-*", cwd=repo).splitlines()
  if not refs:
    raise MaintenanceError("no Ascent V8 rollback ref exists")
  target = refs[0]
  target_sha = git("rev-parse", target, cwd=repo)
  git("switch", "-C", EXPECTED_BRANCH, target_sha, cwd=repo)
  git("submodule", "update", "--init", "--recursive", cwd=repo, timeout=900)
  return {"rolled_back_to": target, "commit": target_sha}


def parse_ssh_command(command: str) -> str:
  parts = shlex.split(command)
  if not parts:
    return "status"
  if len(parts) != 1 or parts[0] not in SAFE_SSH_COMMANDS:
    raise MaintenanceError("command denied; allowed commands: status, logs, update, rollback")
  return parts[0]


def execute(command: str, params: Params, repo: Path = REPO):
  if command == "status":
    return status(params, repo)
  if command == "logs":
    bundle = collect_logs(params, repo)
    contents = bundle.read_bytes()
    bundle.unlink()
    return {
      "bundle_name": bundle.name,
      "encoding": "base64",
      "sha256": hashlib.sha256(contents).hexdigest(),
      "data": base64.b64encode(contents).decode(),
    }
  if command == "update":
    return update(params, repo)
  if command == "rollback":
    return rollback(params, repo)
  raise MaintenanceError("unsupported maintenance command")


def main() -> None:
  from openpilot.common.params import Params

  parser = argparse.ArgumentParser(description="Ascent V8 restricted maintenance endpoint")
  parser.add_argument("command", choices=["status", "logs", "update", "rollback", "ssh-session"])
  args = parser.parse_args()
  params = Params()
  try:
    command = parse_ssh_command(os.environ.get("SSH_ORIGINAL_COMMAND", "")) if args.command == "ssh-session" else args.command
    print(json.dumps(execute(command, params), indent=2, sort_keys=True))
  except Exception as error:
    print(json.dumps({"ok": False, "error": str(error)}, indent=2, sort_keys=True))
    raise SystemExit(1) from error


if __name__ == "__main__":
  main()
