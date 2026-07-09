"""Package and driver management.

Installation is delegated to the environment's installer (``uv pip`` when the
environment is uv-managed, otherwise ``python -m pip``) — FLEX does not invent
its own package distribution.

Drivers are managed at individual-instrument granularity: driver packages ship
all of their drivers, and each driver is enabled/disabled in the active
configuration (``[drivers] enabled = [...]``). Enabling a driver whose parent
package is missing installs that package first.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path

import tomlkit

from flex import components
from flex.ecosystem import ACTIVE_CONFIG, find_config
from flex.log import get_logger
from flex.pkgmanager.catalog import load_catalog

log = get_logger("pkgmanager")


@dataclass
class PackageInfo:
    name: str
    group: str
    summary: str
    installed: str | None  # version if installed
    default: bool = False


@dataclass
class DriverInfo:
    name: str  # e.g. "levylab.lockin"
    package: str  # e.g. "flex-drivers-levylab"
    available: bool  # parent package installed
    enabled: bool  # listed in [drivers] enabled


def installed_version(package: str) -> str | None:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


class PackageManager:
    def __init__(
        self,
        *,
        config_path: Path | None = None,
        runner: Callable[[Sequence[str]], None] | None = None,
    ):
        self._config_path = config_path
        self._run = runner or self._run_installer

    # -- packages ------------------------------------------------------------

    def list_packages(self) -> list[PackageInfo]:
        return [
            PackageInfo(
                name=name,
                group=info.get("group", "Other"),
                summary=info.get("summary", ""),
                installed=installed_version(name),
                default=info.get("default", False),
            )
            for name, info in load_catalog().items()
        ]

    def install(self, *packages: str) -> None:
        missing = [p for p in packages if installed_version(p) is None]
        if not missing:
            log.info("Nothing to install: %s already present", ", ".join(packages))
            return
        log.info("Installing: %s", ", ".join(missing))
        self._run(self._installer_command("install", missing))

    def remove(self, *packages: str) -> None:
        present = [p for p in packages if installed_version(p) is not None]
        if not present:
            return
        log.info("Removing: %s", ", ".join(present))
        self._run(self._installer_command("uninstall", present))

    # -- drivers ---------------------------------------------------------------

    def list_drivers(self) -> list[DriverInfo]:
        """Every known driver: from installed driver packages (live registry)
        plus not-yet-installed packages (static catalog)."""
        enabled = set(self._enabled_drivers())
        drivers: dict[str, DriverInfo] = {}

        for pkg, info in load_catalog().items():
            if "drivers" not in info:
                continue
            available = installed_version(pkg) is not None
            names = info["drivers"]
            if available:  # live registry beats the static list
                names = list(self._package_registry(pkg) or names)
            for name in names:
                drivers[name] = DriverInfo(name, pkg, available, name in enabled)
        return sorted(drivers.values(), key=lambda d: (d.package, d.name))

    def enable_driver(self, name: str) -> DriverInfo:
        """Enable a driver in the active config, installing its package if needed."""
        info = self._find_driver(name)
        if not info.available:
            self.install(info.package)
            info.available = True
        enabled = self._enabled_drivers()
        if name not in enabled:
            self._write_enabled([*enabled, name])
        info.enabled = True
        return info

    def disable_driver(self, name: str) -> None:
        enabled = self._enabled_drivers()
        if name in enabled:
            self._write_enabled([d for d in enabled if d != name])

    def resolve_driver(self, name: str) -> type:
        """Load the instrument class for a driver name like ``"levylab.lockin"``."""
        for registry in components.available("drivers").values():
            reg = registry.load()
            if name in reg:
                return components.load_ref(reg[name]) if isinstance(reg[name], str) else reg[name]
        info = self._find_driver(name, missing_ok=True)
        hint = f" Install it with: flex install {info.package}" if info else ""
        raise components.ComponentError(f"Driver '{name}' is not installed.{hint}")

    # -- internals ---------------------------------------------------------

    def _find_driver(self, name: str, *, missing_ok: bool = False) -> DriverInfo:
        for info in self.list_drivers():
            if info.name == name:
                return info
        if missing_ok:
            return None  # type: ignore[return-value]
        known = ", ".join(d.name for d in self.list_drivers()) or "none"
        raise components.ComponentError(f"Unknown driver '{name}'. Known drivers: {known}")

    def _package_registry(self, package: str) -> dict | None:
        module = package.replace("-", "_")
        for registry in components.available("drivers").values():
            if registry.module.startswith(module):
                try:
                    return registry.load()
                except Exception as e:
                    log.warning("Driver registry of %s failed to load: %s", package, e)
        return None

    def _active_config_file(self) -> Path:
        if self._config_path:
            return self._config_path
        return find_config() or ACTIVE_CONFIG

    def _enabled_drivers(self) -> list[str]:
        path = self._active_config_file()
        if not path.exists():
            return []
        doc = tomlkit.parse(path.read_text(encoding="utf-8"))
        return list(doc.get("drivers", {}).get("enabled", []))

    def _write_enabled(self, names: list[str]) -> None:
        path = self._active_config_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        doc = tomlkit.parse(path.read_text(encoding="utf-8")) if path.exists() else tomlkit.document()
        doc.setdefault("drivers", tomlkit.table())["enabled"] = sorted(names)
        path.write_text(tomlkit.dumps(doc), encoding="utf-8")
        log.info("Enabled drivers -> %s", ", ".join(sorted(names)) or "(none)")

    @staticmethod
    def _installer_command(action: str, packages: list[str]) -> list[str]:
        if shutil.which("uv") and Path(sys.prefix, "pyvenv.cfg").exists():
            cmd = ["uv", "pip", action, "--python", sys.executable]
        else:
            cmd = [sys.executable, "-m", "pip", action]
            if action == "uninstall":
                cmd.append("--yes")
        return [*cmd, *packages]

    @staticmethod
    def _run_installer(command: Sequence[str]) -> None:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"Installer failed ({' '.join(command)}):\n{result.stderr or result.stdout}"
            )
