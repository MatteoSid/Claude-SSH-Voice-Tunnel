import argparse
import io
import os
import subprocess
import sys
import tarfile
import time
import wave
from importlib import resources
from pathlib import Path

from .bridge import RATE, Bridge

REMOTE_DIR = "$HOME/.claude-voice"
MARK = "# >>> claude-voice >>>"
BASHRC = [MARK, 'claude() { "$HOME/.claude-voice/bin/claude-wrap" "$@"; }', "# <<< claude-voice <<<"]


def _device(v):
    return int(v) if v is not None and v.isdigit() else v


def cmd_devices(_):
    import sounddevice as sd
    print(sd.query_devices())


def cmd_test(a):
    import sounddevice as sd
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
    """tar of ~/.claude-voice: bin/claude-wrap, shim/rec, shim/arecord -> rec."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        for name, dest in (("claude-wrap", "bin/claude-wrap"), ("rec", "shim/rec")):
            data = resources.files("claude_voice").joinpath("shim", name).read_bytes().replace(b"\r\n", b"\n")
            ti = tarfile.TarInfo(dest); ti.size = len(data); ti.mode = 0o755
            t.addfile(ti, io.BytesIO(data))
        ln = tarfile.TarInfo("shim/arecord"); ln.type = tarfile.SYMTYPE; ln.linkname = "rec"
        t.addfile(ln)
    return buf.getvalue()


def cmd_install_remote(a):
    block = " ".join("'" + line.replace("'", "'\''") + "'" for line in BASHRC)
    script = (f'd={REMOTE_DIR}; mkdir -p "$d" && rm -f "$d/bin/rec" "$d/bin/arecord" && tar -xf - -C "$d" '
              f'&& grep -qF "{MARK}" ~/.bashrc 2>/dev/null || printf "%s\n" {block} >> ~/.bashrc; '
              f'echo "installed in $d (open a new terminal on the server)"')
    r = subprocess.run(["ssh", *a.ssh_args, a.host, script], input=_remote_bundle())
    sys.exit(r.returncode)


def cmd_daemon(a):
    """Keep a mic bridge + reverse SSH tunnel alive in the background (reconnects forever)."""
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
    if sys.platform != "win32":
        sys.exit("autostart is only implemented for Windows so far (use systemd/launchd to run `claude-voice daemon HOST`).")
    startup = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup/claude-voice.vbs"
    if a.remove:
        startup.unlink(missing_ok=True)
        return print("removed", startup)
    exe = Path(sys.executable).with_name("pythonw.exe")
    extra = " ".join(a.ssh_args)
    startup.write_text(
        f'CreateObject("Wscript.Shell").Run Chr(34) & "{exe}" & Chr(34) & " -m claude_voice daemon {a.host} '
        f'--port {a.port} {extra}", 0, False\n')
    print(f"Installed {startup}\nStarts at next login. Start it now with:  claude-voice daemon {a.host}  (or log out/in)")


def cmd_connect(a):
    """One-off interactive SSH with the tunnel (alternative to the daemon)."""
    bridge = Bridge(device=_device(a.device)).start()
    print(f"Mic bridge on 127.0.0.1:{bridge.port} -> remote port {a.port}")
    cmd = ["ssh", "-t", "-o", "ExitOnForwardFailure=yes", "-R", f"{a.port}:127.0.0.1:{bridge.port}",
           *a.ssh_args, a.host, f"export CLAUDE_VOICE_PORT={a.port}; exec \"$SHELL\" -l"]
    try:
        sys.exit(subprocess.call(cmd))
    finally:
        bridge.shutdown()


def main():
    p = argparse.ArgumentParser(prog="claude-voice", description="Use Claude Code /voice over SSH.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("devices", help="list audio input devices").set_defaults(fn=cmd_devices)

    t = sub.add_parser("test", help="record a short local clip to check the mic")
    t.add_argument("--seconds", type=float, default=3)
    t.add_argument("--out", default="mic-test.wav")
    t.add_argument("--device")
    t.set_defaults(fn=cmd_test)

    for name, fn, h in (("install-remote", cmd_install_remote, "set up the server (shim + `claude` wrapper in ~/.bashrc)"),
                        ("daemon", cmd_daemon, "background mic tunnel to HOST, auto-reconnecting"),
                        ("autostart", cmd_autostart, "run the daemon at login (Windows)"),
                        ("connect", cmd_connect, "one-off SSH session with the mic tunnel")):
        s = sub.add_parser(name, help=h)
        s.add_argument("host", help="[user@]host or ~/.ssh/config alias")
        s.add_argument("ssh_args", nargs="*", help="extra ssh args")
        s.set_defaults(fn=fn)
        if name in ("daemon", "autostart", "connect"):
            s.add_argument("--port", type=int, default=48713, help="remote tunnel port")
        if name in ("daemon", "connect"):
            s.add_argument("--device", help="input device index or name (see `devices`)")
        if name == "autostart":
            s.add_argument("--remove", action="store_true")
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
