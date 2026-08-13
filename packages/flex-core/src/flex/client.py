"""Connect to a running Station server from any PC.

::

    station = flex.connect("tcp://bench-pc:29500")
    station.lockin.gate(0.5)                 # parameters: identical API
    station.lockin.set_ao_dc(1, 0.5)         # any public driver method
    station.subscribe(print)                 # live parameter events

Remote instruments mirror the local Instrument API, so sweeps and
experiments run unchanged against them.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import zmq

from flex.instrument import Instrument
from flex.log import get_logger
from flex.protocols.zmq import ZMQInstrument


class RemoteInstrument(Instrument):
    """Proxy for one instrument hosted by a Station server."""

    def __init__(self, link: ZMQInstrument, name: str, info: dict):
        super().__init__(name)
        self._link = link
        self._remote_class = info["class"]
        self._address = f"{link.address}/{name}"
        for pname, meta in info["parameters"].items():
            getter = (lambda pn=pname: link.call("get", {"instrument": name, "parameter": pn})) \
                if meta["gettable"] else None
            setter = (lambda v, pn=pname: link.call("set", {"instrument": name, "parameter": pn, "value": v})) \
                if meta["settable"] else None
            param = self.add_parameter(pname, getter=getter, setter=setter, unit=meta.get("unit", ""))
            if pname not in self.__dict__ and not hasattr(type(self), pname):
                setattr(self, pname, param)

    def call(self, method: str, *args: Any, **kwargs: Any) -> Any:
        """Call any public method of the remote driver."""
        return self._link.call(
            "call", {"instrument": self.name, "method": method, "args": list(args), "kwargs": kwargs}
        )

    def idn(self) -> dict:
        return self.call("idn")

    def close(self) -> None:
        """The server owns the hardware; nothing to release here."""

    def __getattr__(self, attr: str):
        if attr.startswith("_"):
            raise AttributeError(attr)
        return lambda *args, **kwargs: self.call(attr, *args, **kwargs)

    def __repr__(self) -> str:
        return f"<RemoteInstrument '{self.name}' ({self._remote_class}) @ {self._link.address}>"


class Subscription:
    """A background SUB thread delivering server events to a callback."""

    def __init__(self, address: str, fn: Callable[[dict], None], events: tuple[str, ...]):
        self._stop = threading.Event()
        self._address = address
        self._fn = fn
        self._events = events
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        socket = zmq.Context.instance().socket(zmq.SUB)
        socket.setsockopt(zmq.LINGER, 0)
        socket.connect(self._address)
        for event in self._events:
            socket.setsockopt_string(zmq.SUBSCRIBE, event)
        log = get_logger("client.sub")
        while not self._stop.is_set():
            if socket.poll(100, zmq.POLLIN):
                _, payload = socket.recv_multipart()
                try:
                    self._fn(json.loads(payload))
                except Exception:
                    log.exception("Event callback failed (ignored)")
        socket.close(linger=0)

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2)


class RemoteStation:
    """Proxies for every instrument of a running Station server."""

    def __init__(self, address: str, *, timeout: float = 5.0):
        self._link = ZMQInstrument("link", address, timeout=timeout)
        info = self._link.call("describe")
        self.name = info["station"]
        host = urlsplit(address).hostname or "localhost"
        self._pub_address = f"tcp://{host}:{info['pub_port']}"
        self._subscriptions: list[Subscription] = []
        self.instruments = {
            name: RemoteInstrument(self._link, name, entry)
            for name, entry in info["instruments"].items()
        }

    def get(self, name: str) -> RemoteInstrument:
        if name not in self.instruments:
            have = ", ".join(self.instruments) or "none"
            raise KeyError(f"No instrument '{name}' (served: {have})")
        return self.instruments[name]

    def snapshot(self, *, read: bool = False) -> dict:
        return self._link.call("snapshot", {"read": read})

    def subscribe(self, fn: Callable[[dict], None], events: tuple[str, ...] = ("parameter.update",)) -> Subscription:
        """Stream server events to ``fn(payload_dict)`` on a background thread."""
        sub = Subscription(self._pub_address, fn, events)
        self._subscriptions.append(sub)
        return sub

    def close(self) -> None:
        for sub in self._subscriptions:
            sub.stop()
        self._link.close()

    def __getattr__(self, name: str) -> RemoteInstrument:
        instruments = self.__dict__.get("instruments", {})
        if name in instruments:
            return instruments[name]
        raise AttributeError(f"RemoteStation has no attribute or instrument '{name}'")

    def __dir__(self) -> list[str]:
        return [*super().__dir__(), *self.__dict__.get("instruments", {})]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __repr__(self) -> str:
        return f"<RemoteStation '{self.name}': {', '.join(self.instruments) or 'empty'}>"


def connect(address: str, *, timeout: float = 5.0) -> RemoteStation:
    """Connect to a Station server, e.g. ``flex.connect("tcp://bench-pc:29500")``."""
    return RemoteStation(address, timeout=timeout)
