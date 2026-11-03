"""Local microphone -> TCP (127.0.0.1) bridge. Streams raw 16 kHz mono s16le PCM."""
import socketserver
import sys
import threading

import sounddevice as sd

RATE = 16000
BLOCK = 1600  # 100 ms

_lock = threading.Lock()
_active = 0  # open streams; re-initializing PortAudio would close them


def _refresh_devices():
    # PortAudio reads the device list once. sounddevice has no public refresh, so use its private helpers.
    terminate, initialize = getattr(sd, "_terminate", None), getattr(sd, "_initialize", None)
    if terminate is None or initialize is None:
        return
    if getattr(sd, "_initialized", 1):  # 0 after a failed initialize()
        terminate()
    initialize()


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        global _active
        with _lock:
            if _active == 0 and not isinstance(self.server.device, int):  # an index may move after a refresh
                try:
                    _refresh_devices()
                except sd.PortAudioError as e:
                    print(f"claude-voice: refreshing audio devices failed: {e}", file=sys.stderr)
                    return
            _active += 1
        # The mic is only open while a remote recorder is connected.
        try:
            with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16",
                                   blocksize=BLOCK, device=self.server.device) as stream:
                while True:
                    data, _ = stream.read(BLOCK)
                    self.request.sendall(bytes(data))
        except OSError:
            pass
        except sd.PortAudioError as e:
            print(f"claude-voice: microphone error: {e}", file=sys.stderr)
        finally:
            with _lock:
                _active -= 1


class Bridge(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, port=0, device=None):
        self.device = device
        super().__init__(("127.0.0.1", port), _Handler)  # loopback only, never 0.0.0.0

    @property
    def port(self):
        return self.server_address[1]

    def start(self):
        threading.Thread(target=self.serve_forever, daemon=True).start()
        return self
