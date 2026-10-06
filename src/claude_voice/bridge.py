"""Local microphone -> TCP (127.0.0.1) bridge. Streams raw 16 kHz mono s16le PCM."""
import socketserver
import threading

import sounddevice as sd

RATE = 16000
BLOCK = 1600  # 100 ms


class _Handler(socketserver.BaseRequestHandler):
    def handle(self):
        # The mic is only open while a remote recorder is connected.
        try:
            with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16",
                                   blocksize=BLOCK, device=self.server.device) as stream:
                while True:
                    data, _ = stream.read(BLOCK)
                    self.request.sendall(bytes(data))
        except (BrokenPipeError, ConnectionError, OSError):
            pass


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
