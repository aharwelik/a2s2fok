from pathlib import Path

from tools.ascent_v8_live import build_ssh_command


def test_local_live_command_attaches_persistent_tmux_with_macbook_key():
  command = build_ssh_command("172.20.10.4", Path("/tmp/operator"), "ascent-v8-live", prime=False)

  assert command[0:4] == ["ssh", "-tt", "-i", "/tmp/operator"]
  assert "ServerAliveInterval=5" in command
  assert "ForwardAgent=yes" in command
  assert command[-2] == "comma@172.20.10.4"
  assert command[-1] == "tmux new-session -A -s ascent-v8-live -c /data/openpilot"
  assert not any("ProxyCommand=" in item for item in command)


def test_prime_live_command_uses_same_key_and_tmux_session():
  command = build_ssh_command("comma-0123456789abcdef", Path("/tmp/operator"), "live", prime=True)

  proxy = next(item for item in command if item.startswith("ProxyCommand="))
  assert "ssh.comma.ai" in proxy
  assert "-i /tmp/operator" in proxy
  assert command[-2] == "comma@comma-0123456789abcdef"
  assert command[-1] == "tmux new-session -A -s live -c /data/openpilot"
