"""The official FLEX package catalog.

A static description of every official package: what it is, which group it
belongs to, which components and drivers it provides. Used by the package
manager (and dashboard) to show what is *available*, including packages that
are not installed yet.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from typing import Any


@lru_cache(maxsize=1)
def load_catalog() -> dict[str, dict[str, Any]]:
    """Return the catalog as {package name: info dict}."""
    raw = files("flex.pkgmanager").joinpath("catalog.json").read_text(encoding="utf-8")
    return json.loads(raw)
