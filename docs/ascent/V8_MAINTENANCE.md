# Ascent V8 Restricted Maintenance

V8 keeps SSH available on comma hardware through one pinned Ed25519 public key. No private key is stored in the repository or device image. The corresponding private key remains on the authorized Mac at `~/.ssh/ascent_v8_maintenance`.

The SSH key is forced through `/data/openpilot/tools/ascent_maintenance ssh-session` with OpenSSH `restrict`. It does not provide an arbitrary shell, password login, port forwarding, agent forwarding, or direct CAN commands.

Allowed remote commands are `status`, `logs`, `update`, and `rollback`. Log collection, update, and rollback require `IsOffroad=true`, `IsEngaged=false`, and `ControlsReady=false`. The daemon reasserts the restricted public key and `SshEnabled` every 30 seconds on comma hardware.

From the authorized Mac:

```bash
python3 tools/ascent_v8_ssh.py <comma-ip> status
python3 tools/ascent_v8_ssh.py <comma-ip> logs
python3 tools/ascent_v8_ssh.py <comma-ip> update
python3 tools/ascent_v8_ssh.py <comma-ip> rollback
```

`logs` downloads the allowlisted, checksum-verified archive to `~/Downloads`; it does not include raw CAN, video, credentials, or arbitrary files. Add `--prime` to use a comma device alias or dongle ID through `ssh.comma.ai` instead of a local IP address.

Updates accept only `aharwelik/sunnypilot` branch `ascent-2023-v8-alpha`, a clean worktree, an Ed25519-signed release manifest, an exact OpenDBC gitlink, and the fail-closed audit. A timestamped local rollback ref is created before mutation. A failed audit restores the prior root and submodule state.
