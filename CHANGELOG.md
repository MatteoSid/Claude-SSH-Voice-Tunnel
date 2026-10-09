# Changelog

## 0.1.0 - unreleased

First public release.

- `claude-voice` CLI: `devices`, `test`, `install-remote`, `uninstall-remote`, `daemon`, `autostart`, `connect`.
- Autostart on Windows (Startup folder), macOS (LaunchAgent) and Linux (systemd user unit), one per host.
- Server hook for bash, zsh and fish; `install-remote` works whatever the remote login shell is.
- Extra ssh options are passed after `--`.
- Published on PyPI as `claude-ssh-voice`.
