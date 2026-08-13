"""Component resolution.

The configuration refers to components by short name ("sqlite", "hdf5",
"nextcloud", "levylab.lockin", ...) and this module resolves them to the
actual class. Each group has a fixed list of registries — ``{name:
"module:Class"}`` dicts exported by flex-core itself or by an optional
package (flex-drivers, flex-nextcloud, flex-asana). A registry whose
package isn't installed is simply skipped.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

#: Component group -> registry references, in resolution order.
_REGISTRIES: dict[str, list[str]] = {
    "db": ["flex.db:DB_BACKENDS"],
    "writer": ["flex.datatypes:WRITERS"],
    "storage": ["flex.data:STORAGE", "flex_nextcloud:STORAGE"],
    "comms": ["flex.comms:COMMS", "flex_asana:COMMS"],
    "drivers": ["flex_drivers:CATALOG"],
}

#: Which pip package provides a missing component, for error messages.
_PROVIDERS: dict[str, str] = {
    "storage:nextcloud": "flex-nextcloud",
    "comms:asana": "flex-asana",
    "drivers:*": "flex-drivers",
}


class ComponentError(RuntimeError):
    """A named component could not be found or loaded."""


def available(group: str) -> dict[str, str]:
    """Return {name: dotted ref} for every component in ``group`` whose
    providing package is installed."""
    result: dict[str, str] = {}
    for ref in _REGISTRIES.get(group, []):
        try:
            registry = load_ref(ref)
        except ComponentError:
            continue  # providing package not installed
        result.update(registry)
    return result


def resolve(group: str, name: str) -> Any:
    """Load the component registered as ``name`` in ``group``.

    Raises :class:`ComponentError` with an actionable message when missing,
    including which package provides it if known.
    """
    refs = available(group)
    if name in refs:
        return load_ref(refs[name])

    provider = _PROVIDERS.get(f"{group}:{name}") or _PROVIDERS.get(f"{group}:*")
    hint = f" Install it with: pip install {provider}" if provider else ""
    installed = ", ".join(sorted(refs)) or "none"
    raise ComponentError(
        f"No component '{name}' found for {group} (installed: {installed}).{hint}"
    )


def resolve_driver(name: str) -> type:
    """Load the instrument class for a driver name like ``"levylab.lockin"``.

    A ``"module:Class"`` reference works too, so private driver packages
    need no registration to be used in ``[instruments.*]`` blocks.
    """
    if ":" in name:
        return load_ref(name)
    return resolve("drivers", name)


def load_ref(ref: str) -> Any:
    """Load a dotted reference like ``"flex_asana.comms:AsanaComms"``."""
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
