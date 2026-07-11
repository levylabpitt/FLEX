"""Component resolution.

FLEX packages declare what they provide in the shared package catalog
(``flex.pkgmanager.catalog``): a ``registries`` entry per group, pointing at a
``{name: "module:Class"}`` dict the providing package exports. The ecosystem
configuration refers to components by short name ("sqlite", "hdf5",
"nextcloud", ...) and this module resolves them to the actual class.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any


class ComponentError(RuntimeError):
    """A named component could not be found or loaded."""


def available(group: str) -> dict[str, str]:
    """Return {name: dotted ref} for every component in ``group`` whose
    providing package is installed."""
    from flex.pkgmanager.catalog import load_catalog

    result: dict[str, str] = {}
    for info in load_catalog().values():
        ref = info.get("registries", {}).get(group)
        if not ref:
            continue
        try:
            registry = load_ref(ref)
        except ComponentError:
            continue  # providing package not installed
        result.update(registry)
    return result


def resolve(group: str, name: str) -> Any:
    """Load the component registered as ``name`` in ``group``.

    Raises :class:`ComponentError` with an actionable message when missing,
    including which official package provides it if known.
    """
    refs = available(group)
    if name in refs:
        return load_ref(refs[name])

    hint = _provider_hint(group, name)
    installed = ", ".join(sorted(refs)) or "none"
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
