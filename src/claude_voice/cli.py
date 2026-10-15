import argparse
import io
import os
import re
import subprocess
import sys
import tarfile
import time
import wave
from importlib import resources
from pathlib import Path

from . import __version__

DEFAULT_PORT = 48713


def _sd():
    """Import sounddevice with a helpful message when the PortAudio library is missing (Linux)."""
    try:
        import sounddevice
    except OSError as e:
        sys.exit(f"claude-voice: {e}\nOn Debian/Ubuntu install it with:  sudo apt install libportaudio2")
    return sounddevice


def _device(v):
    return int(v) if v is not None and v.isdigit() else v


def cmd_devices(_):
    print(_sd().query_devices())


def cmd_test(a):
    sd = _sd()
    from .bridge import RATE
    print(f"Recording {a.seconds}s from the microphone... speak now.")
    data = sd.rec(int(a.seconds * RATE), samplerate=RATE, channels=1, dtype="int16",
                  device=_device(a.device))
    sd.wait()
    with wave.open(a.out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(data.tobytes())
    peak = int(abs(data).max())
    print(f"Saved {a.out} (peak level {peak}/32767){' - looks silent!' if peak < 200 else ''}")


def _remote_bundle():
    """tar of ~/.claude-voice: bin/claude-wrap, shim/rec, shim/arecord -> rec, setup.sh."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        for name, dest in (("claude-wrap", "bin/claude-wrap"), ("rec", "shim/rec"), ("setup.sh", "setup.sh")):
            data = resources.files("claude_voice").joinpath("shim", name).read_bytes().replace(b"\r\n", b"\n")
            ti = tarfile.TarInfo(dest); ti.size = len(data); ti.mode = 0o755
            t.addfile(ti, io.BytesIO(data))
        ln = tarfile.TarInfo("shim/arecord"); ln.type = tarfile.SYMTYPE; ln.linkname = "rec"
        t.addfile(ln)
    return buf.getvalue()


def _run_setup(a, action):
    # Works whatever the remote login shell is (bash, zsh, fish): the real logic lives in setup.sh.
    script = f"mkdir -p ~/.claude-voice && tar -xf - -C ~/.claude-voice && sh ~/.claude-voice/setup.sh {action}"
    # A RemoteCommand / RequestTTY in ~/.ssh/config would clash with the command and corrupt the tar on stdin.
    # Given after a.ssh_args: for -o the first value wins, so the user can still override.
    cmd = ["ssh", *a.ssh_args, "-o", "RemoteCommand=none", "-o", "RequestTTY=no", a.host, script]
    sys.exit(subprocess.run(cmd, input=_remote_bundle()).returncode)


def cmd_install_remote(a):
    _run_setup(a, "install")


def cmd_uninstall_remote(a):
    _run_setup(a, "uninstall")


def cmd_daemon(a):
    """Keep a mic bridge + reverse SSH tunnel alive in the background (reconnects forever)."""
    _sd()
    from .bridge import Bridge
    bridge = Bridge(device=_device(a.device)).start()
    log = Path.home() / ".claude-voice" / "daemon.log"
    log.parent.mkdir(exist_ok=True)
    cmd = ["ssh", "-N", "-T", "-o", "BatchMode=yes", "-o", "ExitOnForwardFailure=yes",
           "-o", "ServerAliveInterval=30", "-o", "ServerAliveCountMax=3",
           "-R", f"{a.port}:127.0.0.1:{bridge.port}", *a.ssh_args, a.host]
    flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
    while True:
        with open(log, "ab") as f:
            f.write(f"[{time.ctime()}] starting tunnel to {a.host}\n".encode())
            subprocess.call(cmd, stderr=f, stdin=subprocess.DEVNULL, creationflags=flags)
        time.sleep(5)


def cmd_autostart(a):
    """Register `claude-voice daemon HOST` to start at login (one entry per host)."""
    slug = re.sub(r"[^A-Za-z0-9_.-]", "_", a.host)
    argv = ["-m", "claude_voice", "daemon", a.host, "--port", str(a.port)]
    if a.device is not None:
        argv += ["--device", a.device]
    argv += ["--", *a.ssh_args]
    if sys.platform == "win32":
        path = Path(os.environ["APPDATA"]) / f"Microsoft/Windows/Start Menu/Programs/Startup/claude-voice-{slug}.vbs"
        exe = Path(sys.executable).with_name("pythonw.exe")  # no console window
        cmdline = subprocess.list2cmdline([str(exe), *argv]).replace('"', '""')
        content = f'CreateObject("Wscript.Shell").Run "{cmdline}", 0, False\n'
        start, stop = [], []
        hint = f"Starts at next login. Start it now with:  claude-voice daemon {a.host}  (or log out/in)"
    elif sys.platform == "darwin":
        label = f"com.claude-voice.{slug}"
        path = Path.home() / f"Library/LaunchAgents/{label}.plist"
        args = "".join(f"<string>{_xml(x)}</string>" for x in (sys.executable, *argv))
        content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>{label}</string>
<key>ProgramArguments</key><array>{args}</array>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key><true/>
</dict></plist>
"""
        start = [["launchctl", "load", "-w", str(path)]]
        stop = [["launchctl", "unload", "-w", str(path)]]
        hint = "Running now and at every login."
    else:
        unit = f"claude-voice-{slug}.service"
        path = Path.home() / ".config/systemd/user" / unit
        content = f"""[Unit]
Description=claude-voice microphone tunnel to {a.host}

[Service]
ExecStart={" ".join(_systemd_quote(x) for x in (sys.executable, *argv))}
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
"""
        start = [["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", "--now", unit]]
        stop = [["systemctl", "--user", "disable", "--now", unit]]
        hint = f"Running now and at every login. Status:  systemctl --user status {unit}"

    if a.remove:
        if path.exists():
            for c in stop:
                subprocess.call(c)
            path.unlink()
        return print("removed", path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():  # re-run with new options: stop the old instance, `enable --now` / `load` won't restart it
        for c in stop:
            subprocess.call(c)
    path.write_text(content)
    for c in start:
        subprocess.check_call(c)
    print(f"Installed {path}\n{hint}")


def _xml(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _systemd_quote(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%").replace("$", "$$") + '"'


def cmd_connect(a):
    """One-off interactive SSH with the tunnel (alternative to the daemon)."""
    _sd()
    from .bridge import Bridge
    bridge = Bridge(device=_device(a.device)).start()
    print(f"Mic bridge on 127.0.0.1:{bridge.port} -> remote port {a.port}")
    cmd = ["ssh", "-t", "-o", "ExitOnForwardFailure=yes", "-R", f"{a.port}:127.0.0.1:{bridge.port}",
           *a.ssh_args, "-o", "RemoteCommand=none", a.host, f"export CLAUDE_VOICE_PORT={a.port}; exec \"$SHELL\" -l"]
    try:
        sys.exit(subprocess.call(cmd))
    finally:
        bridge.shutdown()


def main():
    p = argparse.ArgumentParser(
        prog="claude-voice", description="Use Claude Code /voice over SSH.",
        epilog="Pass extra ssh options after `--`, e.g.:  claude-voice daemon myserver -- -p 2222")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("devices", help="list audio input devices").set_defaults(fn=cmd_devices)

    t = sub.add_parser("test", help="record a short local clip to check the mic")
    t.add_argument("--seconds", type=float, default=3)
    t.add_argument("--out", default="mic-test.wav")
    t.add_argument("--device")
    t.set_defaults(fn=cmd_test)

    for name, fn, h in (("install-remote", cmd_install_remote, "set up the server (shim + `claude` wrapper)"),
                        ("uninstall-remote", cmd_uninstall_remote, "remove everything claude-voice put on the server"),
                        ("daemon", cmd_daemon, "background mic tunnel to HOST, auto-reconnecting"),
                        ("autostart", cmd_autostart, "run the daemon at login (Windows, macOS, Linux/systemd)"),
                        ("connect", cmd_connect, "one-off SSH session with the mic tunnel")):
        s = sub.add_parser(name, help=h, description=h)
        s.add_argument("host", help="[user@]host or ~/.ssh/config alias")
        s.add_argument("ssh_args", nargs="*", help="extra ssh args, after `--`")
        s.set_defaults(fn=fn)
        if name in ("daemon", "autostart", "connect"):
            s.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"remote tunnel port (default {DEFAULT_PORT})")
            s.add_argument("--device", help="input device index or name (see `devices`)")
        if name == "autostart":
            s.add_argument("--remove", action="store_true", help="unregister instead")
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
