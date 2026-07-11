"""Ecosystem manifests: ones bundled with flex-core, plus any in a repo
checkout's top-level ``ecosystems/`` folder (found via ``_workspace_root``).
Later directories override earlier ones by name."""

from __future__ import annotations

import tomllib
from importlib.resources import files
from pathlib import Path
from typing import Any


def _dirs() -> list[Any]:
    dirs = [files("flex.pkgmanager").joinpath("ecosystems")]

    from flex.pkgmanager.manager import _workspace_root

    root = _workspace_root()
    if root is not None:
        repo_ecosystems = root / "ecosystems"
        if repo_ecosystems.is_dir():
            dirs.append(repo_ecosystems)
    return dirs


def list_bundled() -> list[dict[str, Any]]:
    """Every known manifest: {file, name, packages}."""
    result: dict[str, dict[str, Any]] = {}
    for eco_dir in _dirs():
        for resource in sorted(eco_dir.iterdir(), key=lambda r: r.name):
            if not resource.name.endswith(".toml"):
                continue
            info = tomllib.loads(resource.read_text(encoding="utf-8")).get("ecosystem", {})
            name = info.get("name", resource.name.removesuffix(".toml"))
            result[name] = {
                "file": str(resource),
                "name": name,
                "packages": info.get("packages", []),
            }
    return list(result.values())


def resolve(name: str) -> Path | None:
    """The manifest path for a known ecosystem by name, or None."""
    found = None
    for eco_dir in _dirs():
        candidate = eco_dir.joinpath(f"{name}.toml")
        if candidate.is_file():
            found = candidate
    if found is not None:
        return Path(str(found))
    for entry in list_bundled():  # filename didn't match; try [ecosystem].name
        if entry["name"] == name:
            return Path(entry["file"])
    return None
