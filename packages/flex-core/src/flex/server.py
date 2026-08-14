"""Host a Station over ZMQ: JSON-RPC commands plus a PUB event stream.

Speaks the same JSON-RPC 2.0 dialect as the LevyLab Instrument-Framework
apps (ACK / IDN / HELP built-ins), so any IF-compatible client — including
:class:`flex.protocols.ZMQInstrument` — can talk to it.

Station-level methods: ``describe``, ``snapshot``, ``listInstruments``.
Instrument methods: ``get`` / ``set`` (parameters) and ``call`` (any public
driver method). Commands for different instruments run concurrently (one
worker thread each); commands for the same instrument are serialized.

Every parameter update is published on the PUB socket as
``[event-name, json]`` with a sequence number, so subscribers can detect
gaps. The event stream is monitoring, not the data record — files and the
metadata store remain authoritative.

Background logging: an ``[instruments.*] log`` list makes the server read
those parameters every ``log_interval`` seconds and write every update to
the configured database (``flex_monitor`` table). The reads go through the
instrument's normal worker queue, so they never collide with commands.
Browse with ``flex monitor``.
"""

from __future__ import annotations

import itertools
import json
import queue
import threading
import time
from datetime import datetime
from typing import Any

import zmq

from flex import __version__ as flex_version
from flex.events import EVENTS
from flex.log import get_logger
from flex.metadata import MonitorRecord
from flex.station import Station

_METHODS = ("ACK", "IDN", "HELP", "describe", "snapshot", "listInstruments", "get", "set", "call")


def _jsonable(obj: Any) -> Any:
    if hasattr(obj, "tolist"):  # numpy arrays and scalars
        return obj.tolist()
    return str(obj)


_POLL = object()  # worker queue marker for a scheduled monitor read


class StationServer:
    def __init__(self, station: Station, *, port: int | None = None, bind: str = "tcp://*",
                 monitor: dict[str, tuple[list[str], float]] | None = None):
        """``monitor`` maps instrument name -> (parameters, interval seconds);
        by default it is derived from the config's ``log``/``log_interval``."""
        self.station = station
        self.log = get_logger(f"server.{station.name}")
        if monitor is None:
            monitor = {
                name: (spec.log, spec.log_interval)
                for name, spec in station.config.instruments.items()
                if spec.log and name in station.instruments
            }
        self.monitor = monitor
        self._logged = {f"{inst}.{p}" for inst, (params, _) in monitor.items() for p in params}
        self._records: queue.Queue = queue.Queue()
        self._monitor_threads: list[threading.Thread] = []
        self._context = zmq.Context.instance()
        self._router = self._context.socket(zmq.ROUTER)
        self._pub = self._context.socket(zmq.PUB)
        for s in (self._router, self._pub):
            s.setsockopt(zmq.LINGER, 0)
        if port is None:
            self.port = self._router.bind_to_random_port(bind)
            self.pub_port = self._pub.bind_to_random_port(bind)
        else:
            self.port, self.pub_port = port, port + 1
            self._router.bind(f"{bind}:{self.port}")
            self._pub.bind(f"{bind}:{self.pub_port}")

        self._replies: queue.Queue = queue.Queue()
        self._events: queue.Queue = queue.Queue()
        self._seq = itertools.count()
        self._running = False
        self._thread: threading.Thread | None = None
        self._workers: dict[str, tuple[threading.Thread, queue.Queue]] = {}
        # worker threads nudge the main loop through an inproc socket, so
        # replies and events flush immediately instead of on the next poll tick
        self._wake_addr = f"inproc://flex-wake-{id(self)}"
        self._waker = self._context.socket(zmq.PULL)
        self._waker.bind(self._wake_addr)
        self._local = threading.local()
        for event in EVENTS:
            station.events.subscribe(event, self._forward_event, name="server")

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Serve on a background thread (tests, notebooks)."""
        self._running = True
        self._start_workers()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.log.info("Serving '%s' on port %d (events on %d)", self.station.name, self.port, self.pub_port)

    def run(self) -> None:
        """Serve on this thread until KeyboardInterrupt."""
        self._running = True
        self._start_workers()
        self.log.info("Serving '%s' on port %d (events on %d)", self.station.name, self.port, self.pub_port)
        try:
            self._loop()
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
        for _worker, q in self._workers.values():
            q.put(None)
        for worker, _q in self._workers.values():
            worker.join(timeout=2)
        for t in self._monitor_threads:
            t.join(timeout=2)
        self._router.close(linger=0)
        self._pub.close(linger=0)
        self._waker.close(linger=0)

    def _start_workers(self) -> None:
        for name in self.station.instruments:
            q: queue.Queue = queue.Queue()
            worker = threading.Thread(target=self._work, args=(name, q), daemon=True)
            worker.start()
            self._workers[name] = (worker, q)
        if self.monitor:
            self._monitor_threads = [
                threading.Thread(target=self._schedule, args=(name, params, interval), daemon=True)
                for name, (params, interval) in self.monitor.items()
            ]
            self._monitor_threads.append(threading.Thread(target=self._write_records, daemon=True))
            for t in self._monitor_threads:
                t.start()

    # -- main loop ---------------------------------------------------------

    def _loop(self) -> None:
        poller = zmq.Poller()
        poller.register(self._router, zmq.POLLIN)
        poller.register(self._waker, zmq.POLLIN)
        while self._running:
            ready = dict(poller.poll(100))
            if ready.get(self._waker):
                while True:
                    try:
                        self._waker.recv(zmq.DONTWAIT)
                    except zmq.Again:
                        break
            if ready.get(self._router):
                identity, _, payload = self._router.recv_multipart()
                self._dispatch(identity, payload)
            self._flush()
        self._flush()

    def _wake(self) -> None:
        sock = getattr(self._local, "wake", None)
        if sock is None:
            sock = self._local.wake = self._context.socket(zmq.PUSH)
            sock.setsockopt(zmq.LINGER, 0)
            sock.connect(self._wake_addr)
        try:
            sock.send(b"", zmq.DONTWAIT)
        except zmq.Again:
            pass  # a wake-up is already pending

    def _flush(self) -> None:
        while True:
            try:
                identity, payload = self._replies.get_nowait()
            except queue.Empty:
                break
            self._router.send_multipart([identity, b"", payload])
        while True:
            try:
                event, payload = self._events.get_nowait()
            except queue.Empty:
                break
            self._pub.send_multipart([event.encode(), payload])

    def _dispatch(self, identity: bytes, payload: bytes) -> None:
        try:
            request = json.loads(payload)
        except Exception:
            self._replies.put((identity, self._error(None, -32700, "Parse error")))
            return
        req_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}
        if method in ("get", "set", "call"):
            name = params.get("instrument")
            if name not in self._workers:
                have = ", ".join(self._workers) or "none"
                self._replies.put((identity, self._error(req_id, -32602, f"No instrument '{name}' (loaded: {have})")))
                return
            self._workers[name][1].put((identity, request))
            return
        try:
            result = self._station_method(method, params)
        except Exception as e:
            self._replies.put((identity, self._error(req_id, -32000, str(e))))
            return
        if result is _UNKNOWN:
            self._replies.put((identity, self._error(req_id, -32601, f"Unknown method '{method}'")))
        else:
            self._replies.put((identity, self._reply(req_id, result)))

    # -- methods -----------------------------------------------------------

    def _station_method(self, method: str, params: dict) -> Any:
        if method == "ACK":
            return "ACK"
        if method == "IDN":
            return {"Manufacturer": "FLEX", "Model": "Station", "Serial Number": self.station.name,
                    "Firmware": flex_version}
        if method == "HELP":
            return list(_METHODS)
        if method == "listInstruments":
            return {n: type(i).__name__ for n, i in self.station.instruments.items()}
        if method == "snapshot":
            return self.station.snapshot(read=bool(params.get("read")))
        if method == "describe":
            return self._describe()
        return _UNKNOWN

    def _describe(self) -> dict:
        instruments = {}
        for name, inst in self.station.instruments.items():
            instruments[name] = {
                "class": f"{type(inst).__module__}.{type(inst).__qualname__}",
                "address": inst.address,
                "log": self.monitor.get(name, ([], 0))[0],
                "parameters": {
                    p.name: {"unit": p.unit, "gettable": p.gettable, "settable": p.settable,
                             "cache": p.cache, "cache_time": p.cache_time}
                    for p in inst.parameters.values()
                },
            }
        return {"station": self.station.name, "pub_port": self.pub_port, "instruments": instruments}

    def _work(self, name: str, q: queue.Queue) -> None:
        inst = self.station.instruments[name]
        while True:
            item = q.get()
            if item is None:
                return
            if item[0] is _POLL:
                try:
                    inst.parameters[item[1]].get()  # emits parameter.update
                except Exception as e:
                    self.log.warning("Monitor read %s.%s failed: %s", name, item[1], e)
                continue
            identity, request = item
            req_id = request.get("id")
            params = request.get("params") or {}
            try:
                method = request["method"]
                if method == "get":
                    result = inst.parameters[params["parameter"]].get()
                elif method == "set":
                    inst.parameters[params["parameter"]].set(params["value"])
                    result = None
                else:
                    attr = params["method"]
                    if attr.startswith("_"):
                        raise ValueError(f"Method '{attr}' is not callable remotely")
                    fn = getattr(inst, attr)
                    if not callable(fn):
                        raise TypeError(f"'{attr}' is not a method of {name}")
                    result = fn(*params.get("args", []), **params.get("kwargs", {}))
                self._replies.put((identity, self._reply(req_id, result)))
            except KeyError as e:
                self._replies.put((identity, self._error(req_id, -32602, f"{name}: no parameter {e}")))
            except Exception as e:
                self._replies.put((identity, self._error(req_id, -32000, f"{name}: {e}")))
            self._wake()

    # -- monitoring --------------------------------------------------------

    def _schedule(self, name: str, params: list[str], interval: float) -> None:
        q = self._workers[name][1]
        next_due = time.monotonic()
        while self._running:
            if time.monotonic() >= next_due:
                for p in params:
                    q.put((_POLL, p))
                next_due = time.monotonic() + interval
            time.sleep(min(0.05, interval / 4))

    def _write_records(self) -> None:
        """Single writer thread: owns the DB connection, drains the record queue.
        Records queue up in memory (not lost) while the DB is unreachable --
        whether it's down at startup or drops out mid-run -- and get flushed
        once it's back, so a `flex serve` restart is never required."""
        store = None
        down = False
        while self._running or not self._records.empty():
            if store is None:
                try:
                    store = self.station.config.build_db()
                    if down:
                        self.log.info("Monitor DB reconnected")
                        down = False
                except Exception as e:
                    if not down:
                        self.log.warning("Monitor DB unavailable (%s) - will keep retrying", e)
                        down = True
                    time.sleep(5)
                    continue
            try:
                record = self._records.get(timeout=0.2)
            except queue.Empty:
                continue
            for attempt, delay in enumerate((0, 0.2, 0.5, 1, 2, 5)):
                time.sleep(delay)
                try:
                    store.record_monitor(record)
                    break
                except Exception as e:
                    if attempt == 0:
                        self.log.warning("Monitor write failed (%s) - retrying", e)
            else:
                self.log.error("Monitor write for %s dropped after repeated failures", record.parameter)
        if store is not None:
            store.close()

    # -- events ------------------------------------------------------------

    def _forward_event(self, *, event: str, **payload) -> None:
        if event == "parameter.update" and payload.get("parameter") in self._logged:
            self._records.put(MonitorRecord(
                parameter=payload["parameter"], value=payload["value"],
                time=datetime.fromtimestamp(payload["ts"]), station=self.station.name,
                unit=payload.get("unit", ""),
            ))
        payload = {k: v.tolist() if hasattr(v, "tolist") else v for k, v in payload.items()}
        payload = {k: v for k, v in payload.items()
                   if isinstance(v, (str, int, float, bool, list, tuple, dict, type(None)))}
        payload.update(seq=next(self._seq), event=event, station=self.station.name)
        self._events.put((event, json.dumps(payload, default=_jsonable).encode()))
        if self._running and threading.current_thread() is not self._thread:
            self._wake()

    # -- json-rpc ----------------------------------------------------------

    @staticmethod
    def _reply(req_id: Any, result: Any) -> bytes:
        return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}, default=_jsonable).encode()

    @staticmethod
    def _error(req_id: Any, code: int, message: str) -> bytes:
        return json.dumps({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}).encode()


class _Unknown:
    pass


_UNKNOWN = _Unknown()
