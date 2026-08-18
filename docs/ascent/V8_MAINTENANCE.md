# Ascent V8 MacBook access and restricted maintenance

V8 keeps SSH available on comma hardware through two pinned Ed25519 public keys. No private key is stored in the repository or device image. Both private keys remain on Anthony's MacBook.

- `~/.ssh/ascent_v8_operator` opens a normal `comma` shell for live development, log retrieval, updates, and persistent tmux sessions.
- `~/.ssh/ascent_v8_maintenance` remains the restricted recovery/update endpoint.

The SSH key is forced through `/data/openpilot/tools/ascent_maintenance ssh-session` with OpenSSH `restrict`. It does not provide an arbitrary shell, password login, port forwarding, agent forwarding, or direct CAN commands.

Allowed remote commands are `status`, `logs`, `update`, and `rollback`. Log collection, update, and rollback require `IsOffroad=true`, `IsEngaged=false`, and `ControlsReady=false`. The daemon reasserts the restricted public key and `SshEnabled` every 30 seconds on comma hardware.

From the authorized Mac:

```bash
python3 tools/ascent_v8_ssh.py <comma-ip> status
python3 tools/ascent_v8_ssh.py <comma-ip> logs
python3 tools/ascent_v8_ssh.py <comma-ip> update
python3 tools/ascent_v8_ssh.py <comma-ip> rollback
```

`status` includes the active native/Chestnut model mode, latest V8 feature snapshot, and automatic calibration-recorder state. `logs` downloads the checksum-verified archive to `~/Downloads`, including the calibration journals; it does not include the full rlog, full-resolution video, credentials, or arbitrary files. Add `--prime` to use a comma device alias or dongle ID through `ssh.comma.ai` instead of a local IP address.

Updates accept only `aharwelik/sunnypilot` branch `ascent-2023-v8-alpha`, a clean worktree, an Ed25519-signed release manifest, an exact OpenDBC gitlink, and the fail-closed audit. A timestamped local rollback ref is created before mutation. A failed audit restores the prior root and submodule state.

For a reconnecting full shell, use:

```bash
ascent-v8-live <16-character-dongle-id> --local-ip <comma-ip>
```

The local hotspot path is tried first. The comma Prime proxy is the fallback. Both routes attach to the same `ascent-v8-live` tmux session, so a Wi-Fi or cellular transition does not lose the shell or its running work. Press Control-C on the MacBook to stop reconnecting.
