"""Serial (COM port) instruments."""

from __future__ import annotations

import serial as pyserial

from flex.instrument import Instrument


class SerialInstrument(Instrument):
    """Base class for instruments on a serial port.

    Args:
        name: Instrument name used in logs, snapshots, and experiments.
        port: Serial port, e.g. ``"COM3"`` or ``"/dev/ttyUSB0"``.
        baudrate: Line speed.
        timeout: Seconds to wait for responses.
        terminator: Line terminator appended to writes and stripped from reads.
        encoding: Text encoding of the protocol.
    """

    def __init__(
        self,
        name: str,
        port: str,
        *,
        baudrate: int = 9600,
        timeout: float = 5.0,
        terminator: bytes = b"\r\n",
        encoding: str = "ascii",
        **kwargs,
    ):
        super().__init__(name, **kwargs)
        self._address = port
        self._terminator = terminator
        self._encoding = encoding
        try:
            self._serial = pyserial.Serial(port, baudrate=baudrate, timeout=timeout)
        except Exception:
            self.log.error("Could not open serial port %s", port)
            raise
        self.log.info("Connected: %s @ %d baud", port, baudrate)

    def write(self, cmd: str) -> None:
        self.log.debug("write: %s", cmd)
        self._serial.write(cmd.encode(self._encoding) + self._terminator)

    def read(self) -> str:
        raw = self._serial.read_until(self._terminator)
        if not raw.endswith(self._terminator):
            raise TimeoutError(f"{self._address}: no response (timeout)")
        response = raw[: -len(self._terminator)].decode(self._encoding).strip()
        self.log.debug("read: %s", response)
        return response

    def query(self, cmd: str) -> str:
        self.write(cmd)
        return self.read()

    def close(self) -> None:
        port = getattr(self, "_serial", None)
        if port is not None:
            self.log.info("Closing %s", self._address)
            port.close()
            self._serial = None
