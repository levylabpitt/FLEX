"""Start, stop, and inspect this PC's station daemon (``flex serve``)."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from flex.config import FlexConfig, load_config


def stop_file(cfg: FlexConfig) -> Path:
    """``flex serve`` shuts down (aborting any run) once this file exists."""
    return Path(cfg.data.root) / "serve.stop"


def log_file(cfg: FlexConfig) -> Path:
    return Path(cfg.data.root) / "serve.log"


def listening(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.3).close()
        return True
    except OSError:
        return False


def status(cfg: FlexConfig | None = None) -> dict:
    """What the daemon is doing right now; never raises."""
    from flex.protocols.zmq import ZMQInstrument
    from flex.runner import RunClient

    cfg = cfg or load_config()
    out = {"station": False, "runner": False, "runner_enabled": cfg.runner.enabled,
           "instruments": [], "failed": {}, "run": None, "last": None}
    if listening(cfg.server.port):
        try:
            with ZMQInstrument("link", f"tcp://127.0.0.1:{cfg.server.port}", timeout=1.0) as link:
                info = link.call("describe")
            out.update(station=True, instruments=list(info["instruments"]), failed=info.get("failed", {}))
        except Exception:
            pass
    if listening(cfg.runner.port):
        try:
            with RunClient(f"tcp://127.0.0.1:{cfg.runner.port}", timeout=1.0,
                           token=cfg.runner.token) as client:
                latest = client.runs(1)
            out["runner"] = True
            if latest:
                out["last"] = {k: latest[0][k] for k in ("id", "name", "origin")}
                if latest[0]["status"] == "running":
                    out["run"] = {"id": latest[0]["id"], "name": latest[0]["name"]}
        except Exception:
            pass
    return out


def start(cfg: FlexConfig | None = None) -> None:
    """Launch ``flex serve`` in the background, without a console window."""
    cfg = cfg or load_config()
    if listening(cfg.server.port):
        return
    if os.name == "nt":
        # via PowerShell, so the daemon is not our child and survives this
        # process's tree being killed
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Start-Process -WindowStyle Hidden -FilePath '{sys.executable}' -ArgumentList '-m','flex','serve','--quiet'"],
            check=True, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        subprocess.Popen([sys.executable, "-m", "flex", "serve", "--quiet"], start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop(cfg: FlexConfig | None = None, wait: float = 20.0) -> bool:
    """Ask the daemon to shut down; True once it has."""
    cfg = cfg or load_config()
    path = stop_file(cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    deadline = time.monotonic() + wait
    while listening(cfg.server.port):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.2)
    return True


def restart(cfg: FlexConfig | None = None) -> None:
    cfg = cfg or load_config()
    if stop(cfg):
        start(cfg)
