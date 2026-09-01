"""Serial transport protocol, pyserial backend, and scripted fake."""

from __future__ import annotations

from typing import Protocol

import serial


_PARITY_MAP = {
    "N": serial.PARITY_NONE,
    "E": serial.PARITY_EVEN,
    "O": serial.PARITY_ODD,
    "M": serial.PARITY_MARK,
    "S": serial.PARITY_SPACE,
}


class SerialTransport(Protocol):
    """Minimal UART seam used by discover/call."""

    def open(self) -> None: ...

    def close(self) -> None: ...

    def write(self, data: bytes) -> None: ...

    def read(self, max_bytes: int = 4096, timeout: float | None = None) -> bytes: ...

    def reset_input_buffer(self) -> None: ...

    def send_break(self, duration: float = 0.25) -> None: ...

    @property
    def is_open(self) -> bool: ...


class PyserialTransport:
    """Production transport wrapping pyserial.Serial."""

    def __init__(
        self,
        port: str,
        baud: int,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: float = 1,
        timeout: float = 0.2,
    ) -> None:
        self.port = port
        self.baud = baud
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        self._ser: serial.Serial | None = None

    def open(self) -> None:
        if self._ser is not None and self._ser.is_open:
            return
        parity_const = _PARITY_MAP.get(self.parity.upper(), serial.PARITY_NONE)
        self._ser = serial.Serial(
            port=self.port,
            baudrate=self.baud,
            bytesize=self.bytesize,
            parity=parity_const,
            stopbits=self.stopbits,
            timeout=self.timeout,
        )

    def close(self) -> None:
        if self._ser is not None:
            try:
                if self._ser.is_open:
                    self._ser.close()
            finally:
                self._ser = None

    def write(self, data: bytes) -> None:
        self._require_open().write(data)

    def read(self, max_bytes: int = 4096, timeout: float | None = None) -> bytes:
        ser = self._require_open()
        old_timeout = ser.timeout
        if timeout is not None:
            ser.timeout = timeout
        try:
            return ser.read(max_bytes)
        finally:
            if timeout is not None:
                ser.timeout = old_timeout

    def reset_input_buffer(self) -> None:
        self._require_open().reset_input_buffer()

    def send_break(self, duration: float = 0.25) -> None:
        self._require_open().send_break(duration)

    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def _require_open(self) -> serial.Serial:
        if self._ser is None or not self._ser.is_open:
            raise RuntimeError("serial port is not open")
        return self._ser


class FakeSerialTransport:
    """Match write substrings in script[baud] FIFO; unmatched write → empty read."""

    def __init__(
        self,
        port: str = "COM0",
        baud: int = 9600,
        script: dict[int, list[tuple[bytes | None, bytes]]] | None = None,
        *,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: float = 1,
        timeout: float = 0.2,
    ) -> None:
        self.port = port
        self.baud = baud
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.timeout = timeout
        # Deep-copy script queues so FIFO consumption is per-instance.
        self._script: dict[int, list[tuple[bytes | None, bytes]]] = {
            b: list(entries) for b, entries in (script or {}).items()
        }
        self.recorded: list[tuple[int, bytes]] = []
        self._rx: bytearray = bytearray()
        self._open = False

    def configure_baud(self, baud: int) -> None:
        self.baud = baud

    def open(self) -> None:
        self._open = True

    def close(self) -> None:
        self._open = False

    def write(self, data: bytes) -> None:
        self._require_open()
        self.recorded.append((self.baud, bytes(data)))
        queue = self._script.get(self.baud)
        if not queue:
            return
        match_key, response = queue[0]
        if match_key is None or match_key in data:
            queue.pop(0)
            self._rx.extend(response)

    def read(self, max_bytes: int = 4096, timeout: float | None = None) -> bytes:
        self._require_open()
        del timeout  # Fake is synchronous; timeout is accepted for API parity.
        if not self._rx:
            return b""
        out = bytes(self._rx[:max_bytes])
        del self._rx[:max_bytes]
        return out

    def reset_input_buffer(self) -> None:
        self._require_open()
        self._rx.clear()

    def send_break(self, duration: float = 0.25) -> None:
        self._require_open()
        del duration
        # Optional break-triggered script entries use match_key=None after a write
        # of b"" is uncommon; break is a no-op on the fake unless scripted via write.
        return

    @property
    def is_open(self) -> bool:
        return self._open

    def _require_open(self) -> None:
        if not self._open:
            raise RuntimeError("serial port is not open")
