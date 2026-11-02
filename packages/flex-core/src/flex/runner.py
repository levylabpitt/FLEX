"""Run submitted scripts in subprocesses, one at a time, so a run outlives whoever started it.

A script defines ``run(station, **params)``; ``station`` joins the servers in
``[runner] servers``. Source, params, log and result of every run are kept
under ``<data root>/runs/``; ``run.status``/``run.log`` events go out on port+1.

Abort drops an ``abort`` file that the child turns into KeyboardInterrupt, so
``finally`` blocks can leave the hardware safe; after a grace period the child
is killed. A file, not a signal: a background process has no console to signal.
"""

from __future__ import annotations

import hashlib
import hmac
import itertools
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import zmq

from flex.log import get_logger
from flex.protocols.zmq import ZMQInstrument

TERMINAL = ("done", "failed", "aborted", "interrupted")
_LEASE_TTL = 30.0  # seconds a station stays leased without a renewal

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, name TEXT, status TEXT, entry TEXT, params TEXT,
    source_hash TEXT, started REAL, finished REAL, error TEXT, result TEXT, dir TEXT, origin TEXT
)
"""
_COLUMNS = ("id", "name", "status", "entry", "params", "source_hash", "started", "finished", "error", "result", "dir",
            "origin")
_ORIGIN_KEYS = ("user", "notebook", "url")  # who/what submitted a run; the client says so, nothing verifies it


def _new_id() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(2)


class RunServer:
    def __init__(self, servers: list[str], *, root: Path | str, port: int | None = None,
                 abort_grace: float = 10.0, call_timeout: float = 120.0, token: str = ""):
        self.servers = servers
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.abort_grace = abort_grace
        self.call_timeout = call_timeout
        self.token = token
        bind = "tcp://*" if token else "tcp://127.0.0.1"  # no token: this PC only
        self.log = get_logger("runner")
        self._db = sqlite3.connect(self.root / "runs.db", check_same_thread=False)
        self._db.execute(_SCHEMA)
        if "origin" not in {r[1] for r in self._db.execute("PRAGMA table_info(runs)")}:
            self._db.execute("ALTER TABLE runs ADD COLUMN origin TEXT")  # a runs.db from before origins
        # a previous server died mid-run: the child may be gone, the record is not trustworthy
        self._db.execute("UPDATE runs SET status = 'interrupted', finished = ? WHERE status = 'running'", (time.time(),))
        self._db.commit()

        context = zmq.Context.instance()
        self._router = context.socket(zmq.ROUTER)
        self._pub = context.socket(zmq.PUB)
        for s in (self._router, self._pub):
            s.setsockopt(zmq.LINGER, 0)
        if port is None:
            self.port = self._router.bind_to_random_port(bind)
            self.pub_port = self._pub.bind_to_random_port(bind)
        else:
            self.port, self.pub_port = port, port + 1
            self._router.bind(f"{bind}:{self.port}")
            self._pub.bind(f"{bind}:{self.pub_port}")

        self._seq = itertools.count()
        self._active: dict[str, Any] | None = None
        self._running = False
        self._thread: threading.Thread | None = None

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self.log.info("Runner on port %d (events on %d)", self.port, self.pub_port)

    def stop(self) -> None:
        self._running = False
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=2)
        if self._active:  # don't leave a script driving hardware with nobody watching
            self._abort_active()
            deadline = time.monotonic() + self.abort_grace + 2
            while self._active and time.monotonic() < deadline:
                self._tick()
                time.sleep(0.05)
        self._router.close(linger=0)
        self._pub.close(linger=0)
        self._db.close()

    def _loop(self) -> None:
        while self._running:
            if self._router.poll(100):
                frames = self._router.recv_multipart()
                if len(frames) == 3:  # [identity, delimiter, payload]; anything else is no REQ client
                    self._router.send_multipart([frames[0], b"", self._handle(frames[2])])
            self._tick()

    # -- requests ----------------------------------------------------------

    def _handle(self, payload: bytes) -> bytes:
        req_id = None
        try:
            request = json.loads(payload)
            req_id = request.get("id")
            method, params = request.get("method"), request.get("params") or {}
            if method != "ACK" and self.token and not hmac.compare_digest(
                    str(params.get("token", "")), self.token):
                return self._error(req_id, -32001, "Unauthorized: wrong or missing runner token")
            if method == "ACK":
                result: Any = "ACK"
            elif method == "submit":
                result = self._submit(params)
            elif method == "runs":
                result = self._list(int(params.get("limit", 20)))
            elif method == "run":
                result = self._get(params["id"], int(params.get("since", 0)))
            elif method == "abort":
                result = self._abort(params.get("id"))
            else:
                return self._error(req_id, -32601, f"Unknown method '{method}'")
            return json.dumps({"jsonrpc": "2.0", "id": req_id, "result": result}).encode()
        except Exception as e:
            return self._error(req_id, -32000, str(e))

    @staticmethod
    def _error(req_id: Any, code: int, message: str) -> bytes:
        return json.dumps({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}).encode()

    def _submit(self, p: dict) -> dict:
        if self._active:
            raise RuntimeError(f"Busy: run {self._active['id']} is still running")
        source, entry = p["source"], p.get("entry") or "run"
        compile(source, "<submitted script>", "exec")  # fail fast on syntax errors
        run_id, token = _new_id(), secrets.token_hex(8)
        leases = self._take_leases(run_id, token)
        try:
            run_dir = self.root / run_id
            run_dir.mkdir()
            (run_dir / "script.py").write_text(source, encoding="utf-8")
            (run_dir / "run.json").write_text(
                json.dumps({"entry": entry, "params": p.get("params") or {}, "servers": self.servers,
                            "call_timeout": self.call_timeout, "lease": token}), encoding="utf-8")
            with open(run_dir / "run.log", "wb") as logfile:
                proc = subprocess.Popen(
                    [sys.executable, "-m", "flex.runchild", str(run_dir)], stdout=logfile,
                    stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                    env={**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"},
                )
        except Exception:
            self._drop_leases(leases, token)
            raise
        origin = p.get("origin")
        origin = {k: str(origin[k])[:300] for k in _ORIGIN_KEYS if origin.get(k)} if isinstance(origin, dict) else {}
        self._db.execute(
            "INSERT INTO runs VALUES (?, ?, 'running', ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)",
            (run_id, p.get("name") or "", entry, json.dumps(p.get("params") or {}),
             hashlib.sha256(source.encode()).hexdigest()[:16], time.time(), str(run_dir),
             json.dumps(origin) if origin else None),
        )
        self._db.commit()
        self._active = {"id": run_id, "proc": proc, "dir": run_dir, "offset": 0, "partial": b"",
                        "aborting": False, "kill_at": 0.0, "leases": leases, "token": token,
                        "renew_at": time.monotonic() + _LEASE_TTL / 3}
        self.log.info("Run %s started (%s)", run_id, p.get("name") or entry)
        self._publish("run.status", run=run_id, status="running")
        return self._record(run_id)

    # -- station leases ------------------------------------------------------
    # A run owns every station server it controls while it lasts; the servers
    # refuse writes from anyone else. The lease expires on its own if we die.

    def _take_leases(self, run_id: str, token: str) -> list:
        links = []
        try:
            for address in self.servers:
                links.append(ZMQInstrument("lease", address, timeout=3.0))
                links[-1].call("leaseAcquire", {"holder": run_id, "token": token, "ttl": _LEASE_TTL})
        except Exception as e:  # all or nothing
            self._drop_leases(links, token)
            raise RuntimeError(f"Cannot start: {e}") from None
        return links

    def _drop_leases(self, links: list, token: str) -> None:
        for link in links:
            try:
                link.call("leaseRelease", {"token": token})
            except Exception as e:
                self.log.warning("Could not release a station lease (it will expire): %s", e)
            link.close()

    def _abort(self, run_id: str | None) -> dict:
        if not self._active or (run_id and run_id != self._active["id"]):
            raise RuntimeError(f"Run {run_id} is not running" if run_id else "No run is running")
        self._abort_active()
        return {"id": self._active["id"], "status": "aborting"}

    def _abort_active(self) -> None:
        a = self._active
        if not a or a["aborting"]:
            return
        a["aborting"] = True
        a["kill_at"] = time.monotonic() + self.abort_grace
        (a["dir"] / "abort").touch()
        self.log.info("Aborting run %s", a["id"])

    # -- records -----------------------------------------------------------

    def _record(self, run_id: str) -> dict:
        row = self._db.execute(f"SELECT {', '.join(_COLUMNS)} FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"No run '{run_id}'")
        rec = dict(zip(_COLUMNS, row, strict=True))
        rec["params"] = json.loads(rec["params"] or "{}")
        rec["result"] = json.loads(rec["result"]) if rec["result"] else None
        rec["origin"] = json.loads(rec["origin"]) if rec["origin"] else {}
        return rec

    def _list(self, limit: int) -> list[dict]:
        ids = [r[0] for r in self._db.execute("SELECT id FROM runs ORDER BY started DESC LIMIT ?", (limit,))]
        return [self._record(i) for i in ids]

    def _get(self, run_id: str, since: int) -> dict:
        rec = self._record(run_id)
        path = Path(rec["dir"]) / "run.log"
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []
        rec.update(lines=len(lines), log=lines[since:])
        return rec

    # -- supervising the active run -----------------------------------------

    def _tick(self) -> None:
        a = self._active
        if not a:
            return
        self._tail(a)
        rc = a["proc"].poll()
        if rc is None:
            if a["aborting"] and time.monotonic() > a["kill_at"]:
                a["proc"].kill()
            if time.monotonic() > a["renew_at"]:
                a["renew_at"] = time.monotonic() + _LEASE_TTL / 3
                for link in a["leases"]:
                    try:
                        link.call("leaseAcquire", {"holder": a["id"], "token": a["token"], "ttl": _LEASE_TTL})
                    except Exception as e:
                        self.log.warning("Could not renew a station lease: %s", e)
            return
        self._drop_leases(a["leases"], a["token"])
        self._tail(a, final=True)
        error, result = None, None
        outcome = a["dir"] / "result.json"
        if outcome.exists():
            data = json.loads(outcome.read_text(encoding="utf-8"))
            error, result = data.get("error"), data.get("result")
        if a["aborting"] or rc == 130:
            status = "aborted"
        elif rc == 0:
            status = "done"
        else:
            status = "failed"
            error = error or f"exited with code {rc}"
        self._db.execute("UPDATE runs SET status = ?, finished = ?, error = ?, result = ? WHERE id = ?",
                         (status, time.time(), error, json.dumps(result) if result is not None else None, a["id"]))
        self._db.commit()
        self.log.info("Run %s %s", a["id"], status)
        self._active = None
        self._publish("run.status", run=a["id"], status=status, error=error)

    def _tail(self, a: dict, final: bool = False) -> None:
        with open(a["dir"] / "run.log", "rb") as f:
            f.seek(a["offset"])
            chunk = f.read()
        a["offset"] += len(chunk)
        *lines, a["partial"] = (a["partial"] + chunk).split(b"\n")
        if final and a["partial"]:
            lines.append(a["partial"])
            a["partial"] = b""
        for line in lines:
            self._publish("run.log", run=a["id"], line=line.decode("utf-8", "replace").rstrip("\r"))

    def _publish(self, event: str, **payload: Any) -> None:
        payload.update(seq=next(self._seq), event=event)
        self._pub.send_multipart([event.encode(), json.dumps(payload).encode()])


class RunClient:
    """Submit and watch runs on a :class:`RunServer`."""

    def __init__(self, address: str, *, timeout: float = 5.0, token: str = ""):
        self._link = ZMQInstrument("runner", address, timeout=timeout)
        self._token = token
        parts = urlsplit(address)
        self._pub_address = f"tcp://{parts.hostname or 'localhost'}:{(parts.port or 0) + 1}"

    def _call(self, method: str, **params):
        return self._link.call(method, {**params, "token": self._token})

    def submit(self, source: str, *, entry: str = "run", params: dict | None = None, name: str = "",
               origin: dict | None = None) -> dict:
        """Run ``entry(station, **params)`` from the script text ``source``. ``origin``
        (``user``, ``notebook``, ``url``) is recorded with the run and shown in the dashboard."""
        return self._call("submit", source=source, entry=entry, params=params or {}, name=name, origin=origin)

    def runs(self, limit: int = 20) -> list[dict]:
        return self._call("runs", limit=limit)

    def run(self, run_id: str, since: int = 0) -> dict:
        """The run record, plus its log lines after line ``since``."""
        return self._call("run", id=run_id, since=since)

    def abort(self, run_id: str | None = None) -> dict:
        return self._call("abort", id=run_id)

    def wait(self, run_id: str, *, poll: float = 0.5, on_log=None) -> dict:
        """Block until the run finishes, passing new log lines to ``on_log``.
        Returns the final record with the complete log."""
        seen = 0
        while True:
            rec = self.run(run_id, seen)
            seen = rec["lines"]
            for line in rec["log"]:
                if on_log:
                    on_log(line)
            if rec["status"] in TERMINAL:
                return self.run(run_id)
            time.sleep(poll)

    def subscribe(self, fn, events: tuple[str, ...] = ("run.status", "run.log")):
        """Stream run events to ``fn(payload_dict)`` on a background thread."""
        from flex.client import Subscription

        return Subscription(self._pub_address, fn, events)

    def close(self) -> None:
        self._link.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
