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

import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from importlib import metadata
from pathlib import Path

import tomlkit

from flex import components
from flex.ecosystem import ACTIVE_CONFIG, find_config
from flex.log import get_logger
from flex.pkgmanager.catalog import load_catalog

log = get_logger("pkgmanager")

#: Where to fetch an official package from when it isn't found in this dev
#: workspace (e.g. a real install, not `uv sync`). Not published anywhere
#: else, so this is a direct source install rather than a registry name.
#: Override with $FLEX_SOURCE_REF if you're tracking a different branch/tag.
SOURCE_REPO = "levylabpitt/flex"
SOURCE_BRANCH = os.environ.get("FLEX_SOURCE_REF", "v2")


@lru_cache(maxsize=1)
def _workspace_root() -> Path | None:
    """The uv workspace root this code is running from, if any."""
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text(encoding="utf-8"):
            return candidate
    return None


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
    package: str  # e.g. "flex-drivers"
    available: bool  # parent package installed
    enabled: bool  # listed in [drivers] enabled


def installed_version(package: str) -> str | None:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def _base_name(name: str) -> str:
    """Strip a `[extra]` suffix, e.g. "flex-db[postgres]" -> "flex-db"."""
    return re.sub(r"\[.*\]$", "", name)


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
        # A name with extras always installs: the base package being present
        # says nothing about the extra's dependencies.
        missing = [p for p in packages if p != _base_name(p) or installed_version(p) is None]
        if not missing:
            log.info("Nothing to install: %s already present", ", ".join(packages))
            return
        log.info("Installing: %s", ", ".join(missing))
        args = [arg for p in missing for arg in self._install_args(p)]
        self._run(self._installer_command("install", args))

    @staticmethod
    def _install_args(name: str) -> list[str]:
        """Args for installing ``name`` (may carry a ``[extra]`` suffix): an
        editable workspace path in a dev checkout, else GitHub source."""
        base = _base_name(name)
        extras = name[len(base):]
        root = _workspace_root()
        if root and (root / "packages" / base / "pyproject.toml").is_file():
            return ["-e", f"{root / 'packages' / base}{extras}"]
        return [
            f"{name} @ git+https://github.com/{SOURCE_REPO}.git"
            f"@{SOURCE_BRANCH}#subdirectory=packages/{base}"
        ]

    def remove(self, *packages: str) -> None:
        present = [_base_name(p) for p in packages if installed_version(_base_name(p)) is not None]
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
        """Load the instrument class for a driver name like ``"levylab.lockin"``.

        Used by explicit, config-driven instrument construction
        (``load_station()``, ``flex instruments --probe``, the dashboard's
        probe button) -- a driver must be enabled first, even if its package
        happens to already be installed. ``CESession`` is exempt: it connects
        whatever the Configure Experiments file says is physically wired up,
        which is its own form of access control.
        """
        if name not in self._enabled_drivers():
            raise components.ComponentError(
                f"Driver '{name}' is not enabled. Enable it with: flex enable {name}"
            )
        try:
            return components.resolve("drivers", name)
        except components.ComponentError:
            pass
        info = self._find_driver(name, missing_ok=True)
        hint = f" Install it with: flex install {info.package}" if info else ""
        raise components.ComponentError(f"Driver '{name}' is not installed.{hint}")

    # -- internals ---------------------------------------------------------

    def _find_driver(self, name: str, *, missing_ok: bool = False) -> DriverInfo | None:
        for info in self.list_drivers():
            if info.name == name:
                return info
        if missing_ok:
            return None
        known = ", ".join(d.name for d in self.list_drivers()) or "none"
        raise components.ComponentError(f"Unknown driver '{name}'. Known drivers: {known}")

    def _package_registry(self, package: str) -> dict | None:
        ref = load_catalog().get(package, {}).get("registries", {}).get("drivers")
        if not ref:
            return None
        try:
            return components.load_ref(ref)
        except components.ComponentError as e:
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
            output = result.stderr or result.stdout
            if "flex.exe" in output and "being used by another process" in output:
                raise RuntimeError(
                    "Can't modify this environment while it's running as flex.exe "
                    "(e.g. a `flex dashboard` launched that way holds its own exe "
                    "file locked on Windows). Restart with `python -m flex dashboard` "
                    "instead, then retry."
                )
            raise RuntimeError(f"Installer failed ({' '.join(command)}):\n{output}")
        _remove_shadowed_console_script()


def _remove_shadowed_console_script() -> None:
    """Every install/uninstall in this environment regenerates Scripts/flex.exe
    on Windows, even when flex-core itself isn't part of the change. install.ps1
    replaces that exe with a flex.cmd shim (`python -m flex`) so `flex ...` never
    self-locks its own launcher while a long-running command like the dashboard
    is up. Delete the regenerated exe again here so PATHEXT keeps resolving
    `flex` to the .cmd, not the .exe uv/pip just brought back."""
    if sys.platform != "win32":
        return
    scripts_dir = Path(sys.executable).parent
    exe = scripts_dir / "flex.exe"
    if exe.exists() and (scripts_dir / "flex.cmd").exists():
        exe.unlink(missing_ok=True)
