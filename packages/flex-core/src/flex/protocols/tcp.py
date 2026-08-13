"""Raw TCP socket instruments (line-based text protocols)."""

from __future__ import annotations

import socket

from flex.instrument import Instrument


class TCPInstrument(Instrument):
    """Base class for instruments speaking a line-based protocol over TCP.

    Args:
        name: Instrument name used in logs, snapshots, and experiments.
        host / port: Network address of the instrument.
        timeout: Seconds to wait for responses.
        terminator: Line terminator appended to writes and stripped from reads.
        encoding: Text encoding of the protocol.
    """

    def __init__(
        self,
        name: str,
        host: str,
        port: int,
        *,
        timeout: float = 5.0,
        terminator: bytes = b"\n",
        encoding: str = "ascii",
        **kwargs,
    ):
        super().__init__(name, **kwargs)
        self._address = f"tcp://{host}:{port}"
        self._terminator = terminator
        self._encoding = encoding
        self._buffer = b""
        try:
            self._socket = socket.create_connection((host, port), timeout=timeout)
        except OSError:
            self.log.error("Could not connect to %s", self._address)
            raise
        self.log.info("Connected: %s", self._address)

    def write(self, cmd: str) -> None:
        self.log.debug("write: %s", cmd)
        self._socket.sendall(cmd.encode(self._encoding) + self._terminator)

    def read(self) -> str:
        while self._terminator not in self._buffer:
            chunk = self._socket.recv(4096)
            if not chunk:
                raise ConnectionError(f"{self._address} closed the connection")
            self._buffer += chunk
        line, self._buffer = self._buffer.split(self._terminator, 1)
        response = line.decode(self._encoding).strip()
        self.log.debug("read: %s", response)
        return response

    def query(self, cmd: str) -> str:
        self.write(cmd)
        return self.read()

    def close(self) -> None:
        sock = getattr(self, "_socket", None)
        if sock is not None:
            self.log.info("Closing %s", self._address)
            try:
                sock.close()
            finally:
                self._socket = None
