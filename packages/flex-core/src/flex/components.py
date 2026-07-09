"""Component resolution.

FLEX packages register their components (DB backends, data writers, storage
backends, drivers, experiment handlers, hooks) through standard Python entry
points. Users never deal with this directly — the ecosystem configuration
refers to components by short name ("sqlite", "hdf5", "nextcloud", ...) and
this module resolves them.
"""

from __future__ import annotations

from importlib import import_module
from importlib.metadata import entry_points
from typing import Any

GROUPS = {
    "db": "flex.db_backends",
    "writer": "flex.writers",
    "storage": "flex.storage",
    "drivers": "flex.drivers",
    "handler": "flex.handlers",
    "hooks": "flex.hooks",
}


class ComponentError(RuntimeError):
    """A named component could not be found or loaded."""


def available(group: str) -> dict[str, Any]:
    """Return {name: entry point} for every installed component in ``group``."""
    group = GROUPS.get(group, group)
    return {ep.name: ep for ep in entry_points(group=group)}


def resolve(group: str, name: str) -> Any:
    """Load the component registered as ``name`` in ``group``.

    Raises :class:`ComponentError` with an actionable message when missing,
    including which official package provides it if known.
    """
    eps = available(group)
    if name in eps:
        try:
            return eps[name].load()
        except Exception as e:
            raise ComponentError(f"Component '{name}' ({group}) failed to load: {e}") from e

    hint = _provider_hint(GROUPS.get(group, group), name)
    installed = ", ".join(sorted(eps)) or "none"
    raise ComponentError(
        f"No component '{name}' found for {group} (installed: {installed}).{hint}"
    )


def load_ref(ref: str) -> Any:
    """Load a dotted reference like ``"flex_asana.hooks:notify_n8n"``."""
    module, _, attr = ref.partition(":")
    try:
        obj = import_module(module)
    except ImportError as e:
        raise ComponentError(f"Cannot import '{module}' from reference '{ref}': {e}") from e
    if attr:
        try:
            for part in attr.split("."):
                obj = getattr(obj, part)
        except AttributeError as e:
            raise ComponentError(f"'{module}' has no attribute '{attr}' (from '{ref}')") from e
    return obj


def _provider_hint(group: str, name: str) -> str:
    from flex.pkgmanager.catalog import load_catalog

    for pkg, info in load_catalog().items():
        if name in info.get("provides", {}).get(group, []):
            return f" Install it with: flex install {pkg}"
    return ""
