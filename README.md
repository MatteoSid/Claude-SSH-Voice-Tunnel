# claude-voice

Use Claude Code's native `/voice` over SSH (including VS Code Remote-SSH terminals).
Claude Code needs a microphone on the machine where `claude` runs; over SSH it fails with
`could not open an audio capture device`. `claude-voice` streams your **local** microphone to the server.

```
local mic -> claude-voice daemon (Python) -> ssh -R tunnel -> server: arecord shim -> claude /voice
```

No WSL, PulseAudio or sox. The server only needs `bash`, `ss`, `unshare` (standard on Ubuntu).

## Install (client)

Requires [uv](https://docs.astral.sh/uv/) and an OpenSSH client with key-based login to the server.

    uv tool install .

Linux client: `sudo apt install libportaudio2`. macOS: allow the terminal to use the microphone.

## Setup (once per server)

    claude-voice devices                      # list microphones
    claude-voice test                         # records mic-test.wav, checks the level
    claude-voice install-remote HOST          # server: shim + `claude` wrapper (adds a block to ~/.bashrc)
    claude-voice autostart HOST               # Windows: start the tunnel daemon at login
    claude-voice daemon HOST                  # ...or run it now / on other OSes (systemd, launchd)

`HOST` is anything `ssh` accepts (e.g. a `~/.ssh/config` alias). Options: `--port` (remote port, default 48713),
`--device`. The daemon keeps a reverse tunnel open and reconnects automatically; log in `~/.claude-voice/daemon.log`.

## Use
In any new terminal on the server (VS Code included): `claude`, then `/voice`, hold space.
Needs a Claude.ai login. Set the dictation language with `/config`.
`claude` is a shell function calling `~/.claude-voice/bin/claude-wrap`: with the tunnel up it enables voice for that
process only; without it, it runs plain `claude`. `CLAUDE_VOICE_OFF=1 claude` forces plain mode.
`claude-voice connect HOST` is a one-off interactive alternative to the daemon.

## Why the wrapper hides /proc/asound/cards
Claude Code uses native ALSA capture whenever `/proc/asound/cards` lists any card, even playback-only (GPU HDMI),
and then never reaches the `arecord` shim (symptom: `ALSA lib ... cannot find card '0'`). The wrapper starts `claude`
in an unprivileged user+mount namespace (same uid) where that file is empty. Side effect: no `sudo` inside that
`claude` while voice is active. Requires unprivileged user namespaces; otherwise it runs without the namespace.

## Security
The bridge listens on 127.0.0.1 only and opens the mic only while a recorder is connected. While the tunnel is up,
processes on the server can request audio: use trusted servers.

## Status
Verified: Windows 11 client, Ubuntu 22.04 server, bash, `/voice` in a VS Code Remote-SSH terminal.
Not done: autostart for macOS/Linux, zsh/fish on the server, VS Code Claude Code extension (uses its own binary).
