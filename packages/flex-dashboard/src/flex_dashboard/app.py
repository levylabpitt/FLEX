"""The FLEX dashboard API — a thin HTTP layer over flex-core services.

All logic lives in flex-core (pkgmanager, ecosystem, metadata); the dashboard
only exposes it to the bundled single-page frontend.
"""

from __future__ import annotations

import tomllib
from importlib.resources import files
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from flex import __version__ as flex_version
from flex.ecosystem import ACTIVE_CONFIG, FlexConfig, find_config, load_config
from flex.pkgmanager import PackageManager


class ConfigText(BaseModel):
    text: str


class ManifestPath(BaseModel):
    path: str


def create_app() -> FastAPI:
    app = FastAPI(title="FLEX Dashboard", version=flex_version)
    manager = PackageManager()

    # -- packages & drivers ------------------------------------------------

    @app.get("/api/packages")
    def packages():
        return [vars(p) for p in manager.list_packages()]

    @app.post("/api/packages/{name}/install")
    def install(name: str):
        try:
            manager.install(name)
        except RuntimeError as e:
            raise HTTPException(500, str(e)) from e
        return {"ok": True}

    @app.post("/api/packages/{name}/remove")
    def remove(name: str):
        try:
            manager.remove(name)
        except RuntimeError as e:
            raise HTTPException(500, str(e)) from e
        return {"ok": True}

    @app.get("/api/drivers")
    def drivers():
        return [vars(d) for d in manager.list_drivers()]

    @app.post("/api/drivers/{name}/enable")
    def enable(name: str):
        try:
            info = manager.enable_driver(name)
        except Exception as e:
            raise HTTPException(400, str(e)) from e
        return vars(info)

    @app.post("/api/drivers/{name}/disable")
    def disable(name: str):
        manager.disable_driver(name)
        return {"ok": True}

    # -- ecosystem / config --------------------------------------------------

    @app.get("/api/config")
    def config():
        source = find_config()
        cfg = load_config()
        return {"source": str(source) if source else None, "config": cfg.model_dump(mode="json")}

    @app.get("/api/config/raw")
    def config_raw():
        source = find_config()
        text = source.read_text(encoding="utf-8") if source else ""
        return {"path": str(source or ACTIVE_CONFIG), "text": text}

    @app.put("/api/config/raw")
    def save_config(body: ConfigText):
        try:
            FlexConfig.model_validate(tomllib.loads(body.text))
        except Exception as e:
            raise HTTPException(422, f"Invalid configuration: {e}") from e
        target = find_config() or ACTIVE_CONFIG
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body.text, encoding="utf-8")
        return {"ok": True, "path": str(target)}

    @app.post("/api/ecosystem/use")
    def use(body: ManifestPath):
        from flex.ecosystem import activate

        if not Path(body.path).exists():
            raise HTTPException(404, f"No manifest at {body.path}")
        try:
            cfg = activate(body.path)
        except Exception as e:
            raise HTTPException(500, str(e)) from e
        return {"ok": True, "ecosystem": cfg.ecosystem.name}

    # -- stations / instruments ---------------------------------------------

    @app.get("/api/stations")
    def stations():
        cfg = load_config()
        return {
            station: {
                name: {"driver": i.driver, "address": i.address}
                for name, i in spec.instruments.items()
            }
            for station, spec in cfg.stations.items()
        }

    @app.post("/api/instruments/{station}/{name}/probe")
    def probe(station: str, name: str):
        cfg = load_config()
        try:
            spec = cfg.stations[station].instruments[name]
        except KeyError as e:
            raise HTTPException(404, f"No instrument {station}/{name}") from e
        try:
            cls = manager.resolve_driver(spec.driver)
            args = (spec.address,) if spec.address else ()
            with cls(name, *args, **spec.options()) as device:
                return {"ok": True, "idn": device.idn()}
        except Exception as e:
            return {"ok": False, "error": str(e)}

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
            }
        finally:
            store.close()

    # -- frontend -----------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    def index():
        return files("flex_dashboard").joinpath("index.html").read_text(encoding="utf-8")

    return app
