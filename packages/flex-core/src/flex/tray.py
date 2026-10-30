"""The FLEX tray app: keeps this PC's station daemon up and opens the dashboard.

Closing the app never touches the daemon (or a run in progress); only
"Stop station" does.
"""

from __future__ import annotations

import os
import sys
import threading
import webbrowser
from pathlib import Path

import pystray
import uvicorn
from PIL import Image, ImageDraw

from flex import daemon
from flex.config import load_config

_COLORS = {"down": "#8a8f98", "up": "#2ea043", "attention": "#d29922", "busy": "#388bfd"}


def _state(s: dict) -> str:
    if not s["station"]:
        return "down"
    if s["failed"] or (s["runner_enabled"] and not s["runner"]):
        return "attention"
    return "busy" if s["run"] else "up"


def _summary(s: dict) -> str:
    station = "station running" if s["station"] else "station stopped"
    if s["failed"]:
        station += f", {len(s['failed'])} instrument(s) failed"
    if not s["runner_enabled"]:
        return station
    runner = f"running {s['run']['name']}" if s["run"] else "runner idle" if s["runner"] else "runner stopped"
    return f"{station}, {runner}"


def _image(color: str) -> Image.Image:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(image).ellipse((6, 6, 58, 58), fill=color)
    return image


def _startup_script() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup/FLEX.vbs"


def _toggle_startup() -> None:
    path = _startup_script()
    if path.exists():
        path.unlink()
        return
    lines = ['Set sh = CreateObject("WScript.Shell")']
    if os.environ.get("FLEX_CONFIG"):
        lines.append(f'sh.Environment("Process")("FLEX_CONFIG") = "{os.environ["FLEX_CONFIG"]}"')
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    lines.append(f'sh.Run """{pythonw}"" -m flex app", 0')
    path.write_text("\r\n".join(lines), encoding="utf-8")


def run(port: int = 8756) -> None:
    if sys.stdout is None:  # started by pythonw: no console to write to
        sys.stdout = sys.stderr = open(os.devnull, "w")
    url = f"http://127.0.0.1:{port}"
    if daemon._listening(port):  # already running: just show it
        webbrowser.open(url)
        return

    from flex.dashboard.app import create_app

    cfg = load_config()
    server = uvicorn.Server(uvicorn.Config(create_app(managed=True), host="127.0.0.1", port=port,
                                           log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    threading.Thread(target=daemon.start, args=(cfg,), daemon=True).start()

    latest = {"station": False, "runner": False, "runner_enabled": cfg.runner.enabled,
              "failed": {}, "run": None}

    def in_background(fn):
        return lambda: threading.Thread(target=fn, args=(cfg,), daemon=True).start()

    def quit_app(icon):
        server.should_exit = True
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Open dashboard", lambda: webbrowser.open(url), default=True),
        pystray.MenuItem(lambda item: _summary(latest), None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Restart station", in_background(daemon.restart)),
        pystray.MenuItem("Stop station", in_background(daemon.stop)),
        pystray.MenuItem("Start with Windows", _toggle_startup, visible=os.name == "nt",
                         checked=lambda item: _startup_script().exists()),
        pystray.MenuItem("Quit (the station keeps running)", quit_app),
    )
    icon = pystray.Icon("flex", _image(_COLORS["down"]), "FLEX", menu)

    def watch(icon):
        icon.visible = True
        shown = None
        while icon.visible:
            latest.update(daemon.status(cfg))
            state = _state(latest)
            if state != shown:
                icon.icon, shown = _image(_COLORS[state]), state
            icon.title = f"FLEX: {_summary(latest)}"
            icon.update_menu()
            threading.Event().wait(3)

    icon.run(watch)
