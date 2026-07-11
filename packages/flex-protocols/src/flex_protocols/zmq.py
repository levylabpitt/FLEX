"""ZMQ instruments: JSON-RPC 2.0 over a REQ socket.

This is the remote-API dialect of the LevyLab Instrument Framework (LabVIEW
apps exposing ACK / IDN / HELP plus instrument-specific methods), but works
with any JSON-RPC-over-ZMQ endpoint.

A JSON-RPC ``error`` response raises :class:`ZMQInstrumentError`; a timeout
recreates the REQ socket (a REQ socket that missed its reply is stuck forever
otherwise) so the next call works again.
"""

from __future__ import annotations

import itertools
import json
from typing import Any

import zmq

from flex.instrument import Instrument


class ZMQInstrumentError(RuntimeError):
    """The instrument answered with a JSON-RPC error."""

    def __init__(self, message: str, code: int | None = None, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class ZMQInstrument(Instrument):
    """Base class for instruments speaking JSON-RPC 2.0 over ZMQ REQ/REP.

    Args:
        name: Instrument name used in logs, snapshots, and experiments.
        address: ZMQ endpoint, e.g. ``"tcp://localhost:29170"``.
        timeout: Seconds to wait for each reply.
        connect_check: Send an ``ACK`` on connect to verify the endpoint.
    """

    def __init__(
        self,
        name: str,
        address: str,
        *,
        timeout: float = 5.0,
        connect_check: bool = True,
        **kwargs,
    ):
        super().__init__(name, **kwargs)
        self._address = address
        self._timeout = timeout
        self._context = zmq.Context.instance()
        self._socket: zmq.Socket | None = None
        self._ids = itertools.count(1)
        self._connect()
        if connect_check:
            try:
                self.call("ACK")
            except Exception:
                self.close()
                raise
        self.log.info("Connected: %s", address)

    # -- transport -----------------------------------------------------------

    def call(self, method: str, params: Any = None, *, timeout: float | None = None) -> Any:
        """Send one JSON-RPC request and return its ``result``.

        Raises :class:`ZMQInstrumentError` on a JSON-RPC error response and
        :class:`TimeoutError` when the instrument does not answer (the socket
        is reset so the next call can succeed).
        """
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": {} if params is None else params,
            # string, not int: the LabVIEW IF app's JSON unflatten is strict
            # about the id's type and silently fails to answer an int id.
            "id": str(next(self._ids)),
        }
        payload = json.dumps(request)
        self.log.debug("-> %s", payload)

        if self._socket is None:
            self._connect()
        try:
            self._socket.send_string(payload)
            wait_ms = int((timeout if timeout is not None else self._timeout) * 1000)
            if not self._socket.poll(wait_ms, zmq.POLLIN):
                raise TimeoutError
            raw = self._socket.recv_string()
        except (TimeoutError, zmq.ZMQError) as e:
            self._reset()
            if isinstance(e, TimeoutError):
                raise TimeoutError(
                    f"{self.name} ({self._address}) did not answer '{method}' within "
                    f"{timeout if timeout is not None else self._timeout}s"
                ) from None
            raise

        self.log.debug("<- %s", raw)
        response = json.loads(raw)
        error = response.get("error")
        if error:
            raise ZMQInstrumentError(
                f"{self.name}: {method} failed: {error.get('message', error)}",
                code=error.get("code"),
                data=error.get("data"),
            )
        return response.get("result")

    # -- Instrument-Framework built-ins ------------------------------------

    def idn(self) -> dict[str, str | None]:
        result = self.call("IDN")
        if isinstance(result, dict):
            return {
                "vendor": result.get("vendor") or result.get("Manufacturer"),
                "model": result.get("model") or result.get("Model") or type(self).__name__,
                "serial": result.get("serial") or result.get("Serial Number"),
                "firmware": result.get("firmware") or result.get("Firmware"),
            }
        return {"vendor": None, "model": str(result), "serial": None, "firmware": None}

    def help(self, command: str | None = None) -> Any:
        """The instrument's own API help (all methods, or one command)."""
        return self.call("HELP", {"command": command} if command else None)

    def close(self) -> None:
        if self._socket is not None:
            self.log.info("Closing %s", self._address)
            self._socket.close(linger=0)
            self._socket = None

    # -- internals ---------------------------------------------------------

    def _connect(self) -> None:
        self._socket = self._context.socket(zmq.REQ)
        self._socket.setsockopt(zmq.LINGER, 0)
        self._socket.connect(self._address)

    def _reset(self) -> None:
        """Recreate the REQ socket after a missed reply (avoids the stuck state)."""
        self.log.warning("Resetting connection to %s", self._address)
        if self._socket is not None:
            self._socket.close(linger=0)
        self._connect()
