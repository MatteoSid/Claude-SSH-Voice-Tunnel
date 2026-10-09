# Contributing

## Development setup

```sh
git clone https://github.com/MatteoSid/Claude-SSH-Voice-Tunnel
cd Claude-SSH-Voice-Tunnel
uv sync
uv run claude-voice --help
```

Layout:
- `src/claude_voice/cli.py`: all commands (runs on your computer)
- `src/claude_voice/bridge.py`: microphone -> TCP bridge
- `src/claude_voice/shim/`: scripts copied to the server by `install-remote` (keep them POSIX/bash, LF line endings)

Before opening a PR, if you touched the shell scripts, run `shellcheck src/claude_voice/shim/*`.
Please describe which client OS / server OS / shell you tested on.

## Releasing (maintainers)

1. Bump `__version__` in `src/claude_voice/__init__.py` and add an entry to `CHANGELOG.md`.
2. Commit, then `git tag vX.Y.Z && git push --tags`.
3. The `Release` workflow builds, publishes to PyPI and creates the GitHub release.
