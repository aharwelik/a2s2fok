import pytest

from openpilot.sunnypilot.system.ascent_maintenance.cli import MaintenanceError, parse_ssh_command, validate_release_manifest
from openpilot.sunnypilot.system.ascent_maintenance.policy import (
  AUTHORIZED_KEY,
  EXPECTED_BRANCH,
  VehicleGateInputs,
  evaluate_mutation_gate,
  validate_authorized_key,
)


def test_embedded_key_is_restricted_public_ed25519():
  assert validate_authorized_key(AUTHORIZED_KEY)
  assert AUTHORIZED_KEY.startswith('restrict,command="/data/openpilot/tools/ascent_maintenance ssh-session" ssh-ed25519 ')
  assert "PRIVATE KEY" not in AUTHORIZED_KEY


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
