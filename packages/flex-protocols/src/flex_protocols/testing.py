"""Test doubles for protocol instruments.

:class:`FakeIFServer` is an in-process ZMQ REP server speaking the
Instrument-Framework JSON-RPC dialect. Use it to test ZMQ drivers without
LabVIEW or hardware::

    with FakeIFServer({"getResults": {"X": [1.0]}}) as server:
        instrument = MyDriver("dev", server.address)
        assert instrument.get_results() == {"X": [1.0]}
        assert server.requests[-1]["method"] == "getResults"
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import zmq


class FakeIFServer:
    """A fake Instrument-Framework app.

    ``handlers`` maps a JSON-RPC method to either a fixed result or a callable
    ``params -> result``. ``ACK``, ``IDN``, and ``HELP`` have sensible
    defaults. A callable may raise to produce a JSON-RPC error response.
    Set :attr:`delay` (seconds) to make replies slow — for timeout tests.
    """

    def __init__(self, handlers: dict[str, Any] | None = None):
        self.handlers = handlers or {}
        self.requests: list[dict] = []
        self.delay = 0.0
        self._context = zmq.Context.instance()
        self._socket = self._context.socket(zmq.REP)
        port = self._socket.bind_to_random_port("tcp://127.0.0.1")
        self.address = f"tcp://127.0.0.1:{port}"
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            if not self._socket.poll(50, zmq.POLLIN):
                continue
            request = json.loads(self._socket.recv_string())
            self.requests.append(request)
            if self.delay:
                time.sleep(self.delay)
            reply: dict[str, Any] = {"jsonrpc": "2.0", "id": request.get("id")}
            try:
                reply["result"] = self._dispatch(request["method"], request.get("params"))
            except KeyError as e:
                reply["error"] = {"code": -32601, "message": f"Unknown method: {e.args[0]}"}
            except Exception as e:
                reply["error"] = {"code": -32000, "message": str(e)}
            self._socket.send_string(json.dumps(reply))

    def _dispatch(self, method: str, params: Any) -> Any:
        if method in self.handlers:
            handler = self.handlers[method]
            return handler(params) if callable(handler) else handler
        if method == "ACK":
            return "ACK"
        if method == "IDN":
            return {"Model": "FakeIF", "Serial Number": "0000"}
        if method == "HELP":
            return sorted({"ACK", "IDN", "HELP", *self.handlers})
        raise KeyError(method)

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)
        self._socket.close(linger=0)

    def __enter__(self) -> FakeIFServer:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
