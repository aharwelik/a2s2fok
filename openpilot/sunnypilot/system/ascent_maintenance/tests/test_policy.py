import subprocess
import tarfile

import pytest

from openpilot.sunnypilot.system.ascent_maintenance.cli import (
  MaintenanceError,
  collect_logs,
  ensure_expected_remote,
  parse_ssh_command,
  status,
  validate_release_manifest,
)
from openpilot.sunnypilot.system.ascent_maintenance.policy import (
  AUTHORIZED_KEY,
  AUTHORIZED_KEYS,
  EXPECTED_BRANCH,
  EXPECTED_REMOTE,
  LEGACY_REMOTE,
  OPERATOR_PUBLIC_KEY,
  VehicleGateInputs,
  evaluate_mutation_gate,
  install_ssh_params,
  validate_authorized_key,
  validate_authorized_keys,
)


def test_embedded_key_is_restricted_public_ed25519():
  assert validate_authorized_key(AUTHORIZED_KEY)
  assert AUTHORIZED_KEY.startswith('restrict,command="/data/openpilot/tools/ascent_maintenance ssh-session" ssh-ed25519 ')
  assert "PRIVATE KEY" not in AUTHORIZED_KEY


def test_macbook_operator_key_is_unrestricted_second_public_key():
  assert validate_authorized_keys(AUTHORIZED_KEYS)
  assert AUTHORIZED_KEYS.splitlines() == [AUTHORIZED_KEY, OPERATOR_PUBLIC_KEY]
  assert OPERATOR_PUBLIC_KEY.startswith("ssh-ed25519 ")
  assert "restrict" not in OPERATOR_PUBLIC_KEY
  assert "command=" not in OPERATOR_PUBLIC_KEY


def test_install_keeps_recovery_and_full_macbook_access():
  params = FakeParams()

  install_ssh_params(params)

  assert params.values["GithubSshKeys"] == AUTHORIZED_KEYS
  assert params.values["SshEnabled"] is True


def test_mutation_gate_is_offroad_disengaged_only():
  assert evaluate_mutation_gate(VehicleGateInputs(True, False, False)).allowed
  for unsafe in (VehicleGateInputs(False, False, False), VehicleGateInputs(True, True, False), VehicleGateInputs(True, False, True)):
    assert not evaluate_mutation_gate(unsafe).allowed


def test_ssh_command_allowlist():
  for command in ("status", "logs", "update", "rollback", ""):
    assert parse_ssh_command(command) in {"status", "logs", "update", "rollback"}
  for command in ("bash", "status; id", "logs extra", "python -c pass"):
    with pytest.raises(MaintenanceError):
      parse_ssh_command(command)


def test_release_manifest_schema():
  manifest = {
    "schema": 1,
    "branch": EXPECTED_BRANCH,
    "root_source_sha": "b" * 40,
    "opendbc_sha": "c" * 40,
    "created_utc": "2026-08-17T00:00:00Z",
  }
  validate_release_manifest(manifest)
  manifest["branch"] = "unapproved"
  with pytest.raises(MaintenanceError):
    validate_release_manifest(manifest)


def test_public_release_target_is_short_lowercase_repo_and_branch():
  assert EXPECTED_REMOTE == "https://github.com/aharwelik/a2s2fok.git"
  assert EXPECTED_BRANCH == "v8"
  assert LEGACY_REMOTE == "https://github.com/aharwelik/sunnypilot.git"


def test_existing_install_migrates_legacy_origin_once(tmp_path):
  subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
  subprocess.run(["git", "-C", str(tmp_path), "remote", "add", "origin", LEGACY_REMOTE], check=True)

  ensure_expected_remote(tmp_path)

  remote = subprocess.run(["git", "-C", str(tmp_path), "remote", "get-url", "origin"], check=True,
                          stdout=subprocess.PIPE, text=True).stdout.strip()
  assert remote == EXPECTED_REMOTE


class FakeParams:
  def __init__(self):
    self.values = {
      "IsOffroad": True,
      "IsEngaged": False,
      "ControlsReady": False,
      "UsbGpuLoading": False,
      "UsbGpuActive": True,
      "AscentV8ShadowStatus": {"schema": 1, "evaluations": 42, "last": {"trajectory": "VALID"}},
      "AscentV8CalibrationStatus": {"schema": 1, "recording": True, "route": "first-drive"},
    }

  def get(self, key):
    return self.values.get(key)

  def get_bool(self, key):
    return bool(self.values.get(key, False))

  def put(self, key, value, block=False):
    self.values[key] = value

  def put_bool(self, key, value, block=False):
    self.values[key] = bool(value)


def test_status_exposes_live_model_and_shadow_telemetry(tmp_path):
  result = status(FakeParams(), tmp_path)

  assert result["model_mode"] == "Chestnut"
  assert result["shadow"]["evaluations"] == 42
  assert result["shadow"]["last"]["trajectory"] == "VALID"
  assert result["calibration"]["route"] == "first-drive"


def test_log_bundle_contains_automatic_calibration_journal(tmp_path):
  repo = tmp_path / "repo"
  repo.mkdir()
  calibration = tmp_path / "calibration"
  calibration.mkdir()
  (calibration / "first-drive.jsonl").write_text('{"schema":1}\n')

  bundle = collect_logs(FakeParams(), repo, tmp_path / "bundles", calibration)

  with tarfile.open(bundle) as archive:
    assert "calibration/first-drive.jsonl" in archive.getnames()
