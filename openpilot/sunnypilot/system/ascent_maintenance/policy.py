from dataclasses import dataclass


EXPECTED_BRANCH = "ascent-2023-v8-alpha"
EXPECTED_REMOTE = "https://github.com/aharwelik/sunnypilot.git"
MAINTENANCE_IDENTITY = "ascent-v8-maintenance"
MAINTENANCE_PUBLIC_KEY = (
  "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIINaJQJhtE03InOP4oafOSYI4ofquzpNLgZ3C512Ml0f " +
  "ascent-v8-maintenance-2026-08-17"
)
FORCED_COMMAND = "/data/openpilot/tools/ascent_maintenance ssh-session"
AUTHORIZED_KEY = f'restrict,command="{FORCED_COMMAND}" {MAINTENANCE_PUBLIC_KEY}'
RELEASE_SIGNER_IDENTITY = "ascent-v8-release"
RELEASE_SIGNATURE_NAMESPACE = "ascent-v8"
RELEASE_PUBLIC_KEY = (
  "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINI52Udmc5ZnIgc+YN5Nt+0ySWfw2HGPOhokmluI1ame " +
  "ascent-v8-release-signing-2026-08-17"
)


@dataclass(frozen=True)
class VehicleGateInputs:
  is_offroad: bool
  is_engaged: bool
  controls_ready: bool


@dataclass(frozen=True)
class VehicleGateDecision:
  allowed: bool
  reasons: tuple[str, ...]


def evaluate_mutation_gate(inputs: VehicleGateInputs) -> VehicleGateDecision:
  reasons: list[str] = []
  if not inputs.is_offroad:
    reasons.append("vehicle_not_offroad")
  if inputs.is_engaged:
    reasons.append("controls_engaged")
  if inputs.controls_ready:
    reasons.append("controls_ready")
  return VehicleGateDecision(not reasons, tuple(reasons))


def validate_authorized_key(value: str) -> bool:
  if ("PRIVATE" + " KEY") in value or "password" in value.lower() or "ssh-rsa" in value:
    return False
  expected_prefix = f'restrict,command="{FORCED_COMMAND}" ssh-ed25519 '
  return value.count("\n") == 0 and value.startswith(expected_prefix) and value == AUTHORIZED_KEY


def install_ssh_params(params) -> None:
  if not validate_authorized_key(AUTHORIZED_KEY):
    raise RuntimeError("invalid embedded Ascent maintenance key policy")
  if params.get("GithubSshKeys") != AUTHORIZED_KEY:
    params.put("GithubSshKeys", AUTHORIZED_KEY, block=True)
  if params.get("GithubUsername") != MAINTENANCE_IDENTITY:
    params.put("GithubUsername", MAINTENANCE_IDENTITY, block=True)
  if not params.get_bool("SshEnabled"):
    params.put_bool("SshEnabled", True, block=True)
