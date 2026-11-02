"""FLEX from a marimo notebook, typically one served by a hub.

::

    station, runs = flex.marimo.connect("ppms")   # [hosts.ppms] in flex.toml
    station.lockin.<Tab>                           # live instruments, with completion
    rec = runs.submit(run, params={"points": 3})   # run() is a function from a cell
    runs.view(rec["id"])                           # status, log, result

Hosts, ports and runner tokens live in ``[hosts.*]`` of the flex.toml that
``$FLEX_CONFIG`` points to, so notebooks never contain them.
"""

from __future__ import annotations

import html
import inspect
import json
import os
import re
import textwrap
import time
import urllib.request
from pathlib import Path

from flex.client import RemoteStation
from flex.config import load_config
from flex.runner import RunClient

_KINDS = {"running": "info", "done": "success", "failed": "danger", "aborted": "warn", "interrupted": "warn"}


def _notebook() -> dict:
    """The hub notebook this kernel serves (its URL and, when the hub's API answers, its title)."""
    try:
        url = json.loads(Path(os.environ["MARIMOHUB_CONTEXT_FILE"]).read_text(encoding="utf-8"))["notebook_url"]
    except (KeyError, OSError, ValueError):
        return {}
    out = {"url": url, "notebook": url.rstrip("/").rsplit("/", 1)[-1]}
    if m := re.match(r"(https?://[^/]+)/projects/([^/]+)/notebooks/([^/?#]+)", url):
        try:  # needs no login on a dev hub; behind real auth the id stays
            with urllib.request.urlopen(f"{m[1]}/api/v1/projects/{m[2]}/notebooks/{m[3]}", timeout=2) as r:
                out["notebook"] = json.load(r)["data"]["meta"]["title"]
        except Exception:
            pass
    return out


class Runs(RunClient):
    def __init__(self, address: str, *, user: str = "", **kwargs):
        """``user``: who is running (else ``$FLEX_USER``). The hub does not tell a kernel who is
        using it, so this is whatever the notebook says."""
        super().__init__(address, **kwargs)
        self.user = user

    def submit(self, source, *, entry: str = "run", params: dict | None = None, name: str = "",
               origin: dict | None = None) -> dict:
        """Run ``entry(station, **params)`` from script text, or from a function defined in a
        cell. The function runs in its own process: import what it needs inside it."""
        if callable(source):
            entry, name = source.__name__, name or source.__name__
            source = textwrap.dedent(inspect.getsource(source))
        origin = {"user": self.user or os.environ.get("FLEX_USER", ""), **_notebook(), **(origin or {})}
        return super().submit(source, entry=entry, params=params, name=name, origin=origin)

    def view(self, run_id: str | None = None):
        """A marimo element with the run's status, log and result (default: the latest run).
        Reference a ``mo.ui.refresh`` in the same cell to keep it updating."""
        import marimo as mo

        if run_id is None:
            latest = self.runs(1)
            if not latest:
                return mo.md("_No runs yet._")
            run_id = latest[0]["id"]
        rec = self.run(run_id)
        took = (rec["finished"] or time.time()) - rec["started"]
        head = f"**{rec['status']}** · `{rec['id']}` · {rec['name']} · {took:.0f}s"
        if who := " · ".join(filter(None, (rec["origin"].get("user"), rec["origin"].get("notebook")))):
            head += f"<br>by {html.escape(who)}"
        if rec["error"]:
            head += f"<br>{html.escape(rec['error'])}"
        log = "\n".join(rec["log"][-200:])
        parts = [mo.callout(mo.md(head), kind=_KINDS.get(rec["status"], "neutral")),
                 mo.Html(f"<pre style='max-height:420px;overflow:auto;font-size:12px'>{html.escape(log)}</pre>")]
        if rec["result"] is not None:
            parts.append(mo.json(rec["result"]))
        return mo.vstack(parts)


def connect(host: str, *, user: str = "", config: str | Path | None = None) -> tuple[RemoteStation, Runs]:
    """The live station and the runner of the PC named ``[hosts.<host>]`` in the config.
    ``user`` is recorded with every run you submit."""
    cfg = load_config(config)
    if host not in cfg.hosts:
        raise KeyError(f"No [hosts.{host}] in {cfg.source or 'the default config'} "
                       f"(have: {', '.join(cfg.hosts) or 'none'})")
    h = cfg.hosts[host]
    station = RemoteStation(f"tcp://{h.host}:{h.station_port}")
    return station, Runs(f"tcp://{h.host}:{h.runner_port}", token=h.token, user=user)
