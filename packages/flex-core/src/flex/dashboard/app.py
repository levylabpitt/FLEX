"""The dashboard's HTTP API, served by the tray app.

The Station tab connects to this PC's station server or any other PC's,
builds instrument panels from its ``describe``, and bridges its event stream
to the browser over a WebSocket.
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import threading
import tomllib
from importlib.resources import files
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from flex import __version__ as flex_version
from flex import components, daemon
from flex.client import connect
from flex.config import USER_CONFIG, FlexConfig, find_config, load_config
from flex.log import get_logger
from flex.protocols.zmq import ZMQInstrumentError
from flex.runner import RunClient

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "[::1]"}
_HOST = re.compile(r"^[\w.\-]+$")


class ConfigText(BaseModel):
    text: str


class ParamOp(BaseModel):
    address: str
    instrument: str
    parameter: str


class ParamSet(ParamOp):
    value: Any


class _StationHub:
    """Lazy connections to station servers, fanning their events out to
    websocket clients. One ZMQ link per server, guarded by a lock (REQ is
    lockstep and dashboard requests run on a thread pool)."""

    def __init__(self):
        self.loop: asyncio.AbstractEventLoop | None = None
        self.log = get_logger("dashboard.stations")
        self._connections: dict[str, tuple[Any, threading.Lock]] = {}
        self._clients: set[asyncio.Queue] = set()
        self._lock = threading.Lock()

    def connection(self, address: str):
        with self._lock:
            entry = self._connections.get(address)
            if entry is None:
                conn = connect(address, timeout=3.0)
                conn.subscribe(lambda e, a=address: self._fan_out(e, a), events=("",))
                entry = self._connections[address] = (conn, threading.Lock())
            return entry

    def drop(self, address: str) -> None:
        """Forget a dead connection so the next request reconnects."""
        with self._lock:
            entry = self._connections.pop(address, None)
        if entry is not None:
            with contextlib.suppress(Exception):
                entry[0].close()

    def _fan_out(self, event: dict, address: str) -> None:
        event["address"] = address
        if self.loop is None:
            return
        for q in list(self._clients):
            self.loop.call_soon_threadsafe(self._offer, q, event)

    @staticmethod
    def _offer(q: asyncio.Queue, event: dict) -> None:
        with contextlib.suppress(asyncio.QueueFull):
            q.put_nowait(event)

    def register(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._clients.add(q)
        return q

    def unregister(self, q: asyncio.Queue) -> None:
        self._clients.discard(q)

    def close(self) -> None:
        for address in list(self._connections):
            self.drop(address)


def create_app() -> FastAPI:
    hub = _StationHub()

    @contextlib.asynccontextmanager
    async def _lifespan(app: FastAPI):
        hub.loop = asyncio.get_running_loop()
        yield
        hub.close()

    app = FastAPI(title="FLEX Dashboard", version=flex_version, lifespan=_lifespan)

    @app.middleware("http")
    async def _localhost_only(request: Request, call_next):
        # Reject foreign Host headers (CSRF / DNS rebinding on a localhost tool).
        host = (request.headers.get("host") or "").lower()
        if ":" in host and not host.endswith("]"):
            host = host.rpartition(":")[0]
        if host not in _LOCAL_HOSTS:
            return JSONResponse({"detail": "Forbidden host"}, status_code=403)
        # a JSON content type forces a CORS preflight, so other sites cannot trigger writes
        if request.method in ("POST", "PUT") and "application/json" not in request.headers.get("content-type", ""):
            return JSONResponse({"detail": "JSON required"}, status_code=403)
        return await call_next(request)

    # -- stations ------------------------------------------------------------

    @app.get("/api/stations")
    def station(host: str = "", port: int = 0):
        """Describe a station server: the one at ``host:port``, or this PC's own."""
        local_port = load_config().server.port
        host, port = host or "localhost", port or local_port
        view = {"host": host, "port": port, "local": host in _LOCAL_HOSTS and port == local_port}
        address = f"tcp://{host}:{port}"
        try:
            if not _HOST.match(host) or not 0 < port < 65536:
                raise ValueError("Not a valid address")
            hub.drop(address)  # reconnect: the station may have restarted with other instruments
            conn, lock = hub.connection(address)
            with lock:
                info = conn.describe()
        except Exception as e:
            hub.drop(address)
            return {**view, "address": address, "ok": False, "error": str(e)}
        return {**view, "address": address, "ok": True, "station": info["station"],
                "instruments": info["instruments"], "failed": info.get("failed", {}),
                "lease": info.get("lease")}

    @app.post("/api/stations/get")
    def station_get(op: ParamOp):
        try:
            conn, lock = hub.connection(op.address)
            with lock:
                value = conn.instruments[op.instrument].parameters[op.parameter].get()
        except KeyError as e:
            raise HTTPException(404, f"No such instrument/parameter: {e}") from e
        except Exception as e:
            raise HTTPException(502, str(e)) from e
        return {"value": value}

    @app.post("/api/stations/set")
    def station_set(op: ParamSet):
        try:
            conn, lock = hub.connection(op.address)
            with lock:
                conn.instruments[op.instrument].parameters[op.parameter].set(op.value)
        except KeyError as e:
            raise HTTPException(404, f"No such instrument/parameter: {e}") from e
        except Exception as e:
            raise HTTPException(502, str(e)) from e
        return {"ok": True}

    @app.websocket("/ws/events")
    async def ws_events(ws: WebSocket):
        await ws.accept()
        q = hub.register()
        try:
            while True:
                await ws.send_json(await q.get())
        except WebSocketDisconnect:
            pass
        finally:
            hub.unregister(q)

    # -- drivers ------------------------------------------------------------

    @app.get("/api/drivers")
    def drivers():
        refs = components.available("drivers")
        return [{"name": name, "ref": refs[name]} for name in sorted(refs)]

    @app.post("/api/drivers/{name}/probe")
    def probe_driver(name: str):
        try:
            cls = components.resolve_driver(name)
            with cls(name) as device:
                return {"ok": True, "idn": device.idn()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # -- config --------------------------------------------------------------

    @app.get("/api/config/raw")
    def config_raw():
        source = find_config()
        text = source.read_text(encoding="utf-8") if source else ""
        return {"path": str(source or USER_CONFIG), "text": text}

    @app.put("/api/config/raw")
    def save_config(body: ConfigText):
        """Save flex.toml and restart an idle station so the edit takes effect. It is stopped
        before the write, while its old ports and data root still apply."""
        try:
            FlexConfig.model_validate(tomllib.loads(body.text))
        except Exception as e:
            raise HTTPException(422, f"Invalid configuration: {e}") from e
        state = daemon.status()
        restart = state["station"] and not state["run"]
        if restart:
            daemon.stop()
        target = find_config() or USER_CONFIG
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body.text, encoding="utf-8")
        if restart:
            daemon.start()
        return {"ok": True, "path": str(target), "restarted": restart, "run": state["run"]}

    # -- experiments -----------------------------------------------------

    @app.get("/api/experiments")
    def experiments(user: str = "", limit: int = 50):
        store = load_config().build_db()
        try:
            return [vars(e) for e in store.list_experiments(user=user or None, limit=limit)]
        finally:
            store.close()

    @app.get("/api/experiments/{experiment_id}")
    def experiment_detail(experiment_id: str):
        store = load_config().build_db()
        try:
            exp = store.get_experiment(experiment_id)
            if exp is None:
                raise HTTPException(404, f"No experiment {experiment_id}")
            return {
                "experiment": vars(exp),
                "measurements": [
                    {**vars(m), "file": vars(m.file) if m.file else None}
                    for m in store.list_measurements(experiment_id)
                ],
                "notes": [vars(n) for n in store.list_notes(experiment_id)],
                "cells": [vars(c) for c in store.list_cells(experiment_id)],
                "logs": [vars(entry) for entry in store.list_logs(experiment_id)],
                "instruments": [vars(i) for i in store.list_instruments(experiment_id)],
            }
        finally:
            store.close()

    # -- station daemon -------------------------------------------------------

    @app.get("/api/app")
    def app_status():
        return daemon.status()

    @app.post("/api/app/{action}")
    def app_control(action: str):
        if action not in ("start", "stop", "restart"):
            raise HTTPException(404, f"No action '{action}'")
        getattr(daemon, action)()
        return {"ok": True}

    # -- runs (this PC's runner) ------------------------------------------------

    def _runner(call):
        cfg = load_config()
        try:
            with RunClient(f"tcp://127.0.0.1:{cfg.runner.port}", timeout=2.0, token=cfg.runner.token) as client:
                return call(client)
        except ZMQInstrumentError as e:
            raise HTTPException(409, str(e)) from None
        except Exception as e:
            raise HTTPException(503, f"Runner not reachable: {e}") from None

    @app.get("/api/runs")
    def runs():
        return _runner(lambda c: c.runs(30))

    @app.get("/api/runs/{run_id}")
    def run(run_id: str, since: int = 0):
        return _runner(lambda c: c.run(run_id, since))

    @app.post("/api/runs/abort")
    def abort_run():
        return _runner(lambda c: c.abort())

    # -- frontend -----------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def index():
        return files("flex.dashboard").joinpath("index.html").read_text(encoding="utf-8")

    return app
