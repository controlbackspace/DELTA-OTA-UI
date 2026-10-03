"""Host-timestamped capture of an ESP32's serial output.

The firmware prints no timestamps, so every line is stamped on the host the
moment it arrives ("[+12.345] ..."); serial_parse understands that prefix.
The serial object is injectable so the logic is tested without hardware.
"""
from __future__ import annotations

import re
import time
from pathlib import Path


class SerialCapture:
    def __init__(self, port: str, baud: int = 115200, log_path: Path | None = None, serial_factory=None):
        self.port, self.baud = port, baud
        self.log_path = Path(log_path) if log_path else None
        self._factory = serial_factory
        self.ser = None
        self.t0 = time.perf_counter()

    def open(self):
        if self._factory is None:
            import serial                                       # pyserial
            self._factory = serial.Serial
        self.ser = self._factory(self.port, self.baud, timeout=0.2)
        self.ser.dtr = False                                    # keep the board out of the bootloader
        self.t0 = time.perf_counter()
        return self

    def reset_board(self) -> None:
        """Pulse EN via RTS (same sequence as tools/reset_device.py)."""
        self.ser.dtr = False
        self.ser.rts = True
        time.sleep(0.1)
        self.ser.rts = False
        self.t0 = time.perf_counter()

    def capture(self, seconds: float, until: str | None = None) -> str:
        """Read for up to `seconds`, or until a line matches the regex `until`.
        Returns the stamped text and writes it to log_path."""
        pat = re.compile(until) if until else None
        lines, buf = [], b""
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            chunk = self.ser.read(256)
            if not chunk:
                continue
            buf += chunk
            while b"\n" in buf:
                raw, buf = buf.split(b"\n", 1)
                text = raw.decode("utf-8", errors="replace").rstrip("\r")
                lines.append(f"[+{time.perf_counter() - self.t0:.3f}] {text}")
                if pat and pat.search(text):
                    return self._finish(lines)
        return self._finish(lines)

    def _finish(self, lines: list[str]) -> str:
        text = "\n".join(lines) + ("\n" if lines else "")
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.write_text(text, encoding="utf-8")
        return text

    def close(self) -> None:
        if self.ser is not None:
            self.ser.close()
            self.ser = None
