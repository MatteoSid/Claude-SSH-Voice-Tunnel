# Changelog

## 0.1.1 - 2026-10-15

- Fix `autostart` not applying new options (e.g. `--port`) on re-run: the already-running instance is now stopped before the unit is rewritten. Thanks to [@devilteo911](https://github.com/devilteo911).

## 0.1.0 - 2026-10-09

First public release.

- `claude-voice` CLI: `devices`, `test`, `install-remote`, `uninstall-remote`, `daemon`, `autostart`, `connect`.
- Autostart on Windows (Startup folder), macOS (LaunchAgent) and Linux (systemd user unit), one per host.
- Server hook for bash, zsh and fish; `install-remote` works whatever the remote login shell is.
- Extra ssh options are passed after `--`.
- Published on PyPI as `claude-ssh-voice`.
