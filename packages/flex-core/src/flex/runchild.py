"""Subprocess entry point for one run: ``python -m flex.runchild <run dir>``."""

from __future__ import annotations

import json
import runpy
import signal
import sys
import traceback
from pathlib import Path


def _jsonable(obj):
    return obj.tolist() if hasattr(obj, "tolist") else str(obj)


def _interrupt(signum, frame):
    raise KeyboardInterrupt


def main(run_dir: str) -> int:
    d = Path(run_dir)
    for name in ("SIGBREAK", "SIGTERM"):
        if hasattr(signal, name):
            signal.signal(getattr(signal, name), _interrupt)
    spec = json.loads((d / "run.json").read_text(encoding="utf-8"))
    outcome: dict = {}
    station = None
    code = 0
    try:
        namespace = runpy.run_path(str(d / "script.py"), run_name="__flex_run__")
        fn = namespace.get(spec["entry"])
        if not callable(fn):
            raise NameError(f"The script defines no function '{spec['entry']}'")
        from flex.client import StationGroup

        station = StationGroup(spec["servers"])
        outcome["result"] = fn(station, **spec["params"])
    except KeyboardInterrupt:
        outcome["error"] = "aborted"
        code = 130
    except BaseException as e:
        traceback.print_exc()
        outcome["error"] = f"{type(e).__name__}: {e}"
        code = 1
    finally:
        if station is not None:
            station.close()
    (d / "result.json").write_text(json.dumps(outcome, default=_jsonable), encoding="utf-8")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
