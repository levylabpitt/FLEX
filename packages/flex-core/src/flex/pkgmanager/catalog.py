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
    """Return the catalog as {package name: info dict}.

    Starts from the built-in catalog shipped with flex-core, then merges in
    an optional project-local ``catalog.local.json`` next to the active
    ecosystem config, if one exists -- lets a lab register its own packages
    and drivers without editing an installed package.
    """
    raw = files("flex.pkgmanager").joinpath("catalog.json").read_text(encoding="utf-8")
    catalog: dict[str, dict[str, Any]] = json.loads(raw)

    from flex.ecosystem import find_config

    config_path = find_config()
    if config_path is not None:
        local_path = config_path.parent / "catalog.local.json"
        if local_path.exists():
            catalog.update(json.loads(local_path.read_text(encoding="utf-8")))
    return catalog
