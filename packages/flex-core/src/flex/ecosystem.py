"""FLEX ecosystem configuration.

An **ecosystem** is a bundle of packages + configuration described by a single
TOML manifest (e.g. ``ecosystems/levylab.toml`` in the FLEX repository). A lab
activates one with ``flex ecosystem use <file>`` — the listed packages are
installed and the manifest becomes the *active configuration*.

With no configuration at all, FLEX still works: SQLite metadata, HDF5 data
files, local storage under the user data directory.

Active configuration resolution order:
    1. explicit path argument
    2. ``$FLEX_CONFIG``
    3. ``./flex.toml``
    4. ``%LOCALAPPDATA%/flex/config.toml`` (per-platform user data dir)
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Any

from platformdirs import user_data_path
from pydantic import BaseModel, ConfigDict, Field

from flex import components
from flex.log import get_logger

if TYPE_CHECKING:
    from flex.events import EventBus

APP_DIR: Path = user_data_path("flex", appauthor=False)
ACTIVE_CONFIG: Path = APP_DIR / "config.toml"


def default_data_root() -> Path:
    return APP_DIR / "data"


class _Section(BaseModel):
    """Config section that lets backends define their own extra options."""

    model_config = ConfigDict(extra="allow")

    def options(self) -> dict[str, Any]:
        """Backend-specific options (everything beyond the declared fields)."""
        return dict(self.model_extra or {})


class EcosystemInfo(_Section):
    name: str = "default"
    packages: list[str] = Field(default_factory=list)


class LabInfo(_Section):
    name: str = ""
    station: str = ""


class DBConfig(_Section):
    backend: str = "sqlite"


class StorageConfig(_Section):
    backend: str = "local"


class DataConfig(_Section):
    writer: str = "hdf5"
    root: Path = Field(default_factory=default_data_root)


class ExpConfig(_Section):
    handler: str = "default"
    strict_metadata: bool = False


class CommsConfig(_Section):
    backend: str = "none"


class DriversConfig(_Section):
    enabled: list[str] = Field(default_factory=list)


class InstrumentConfig(_Section):
    driver: str
    address: str = ""


class StationConfig(_Section):
    instruments: dict[str, InstrumentConfig] = Field(default_factory=dict)


class FlexConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    ecosystem: EcosystemInfo = Field(default_factory=EcosystemInfo)
    lab: LabInfo = Field(default_factory=LabInfo)
    db: DBConfig = Field(default_factory=DBConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    exp: ExpConfig = Field(default_factory=ExpConfig)
    comms: CommsConfig = Field(default_factory=CommsConfig)
    hooks: dict[str, list[str]] = Field(default_factory=dict)
    drivers: DriversConfig = Field(default_factory=DriversConfig)
    stations: dict[str, StationConfig] = Field(default_factory=dict)

    source: Path | None = Field(default=None, exclude=True)

    # -- component builders -------------------------------------------------

    def build_db(self):
        """Instantiate the configured metadata store."""
        cls = components.resolve("db", self.db.backend)
        return cls(data_root=self.data.root, **self.db.options())

    def build_writer(self, name: str | None = None):
        """Instantiate a data writer (the configured default unless overridden)."""
        cls = components.resolve("writer", name or self.data.writer)
        return cls(**self.data.options())

    def build_storage(self):
        """Instantiate the configured storage backend."""
        cls = components.resolve("storage", self.storage.backend)
        opts = self.storage.options()
        root = opts.pop("root", self.data.root)  # explicit [storage] root wins
        return cls(root=root, **opts)

    def build_comms(self):
        """Instantiate the configured comms backend (none by default)."""
        cls = components.resolve("comms", self.comms.backend)
        return cls(**self.comms.options())

    def build_bus(self) -> EventBus:
        """Create an EventBus with all configured hooks subscribed."""
        from flex.events import EventBus

        bus = EventBus()
        for event, refs in self.hooks.items():
            key = event.replace("on_", "", 1).replace("_", ".", 1) if event.startswith("on_") else event
            for ref in refs:
                try:
                    bus.subscribe(key, components.load_ref(ref), name=ref)
                except Exception as e:
                    get_logger("ecosystem").warning("Hook '%s' not loaded: %s", ref, e)
        return bus


def find_config(path: str | Path | None = None) -> Path | None:
    """Locate the active configuration file, or None if running on pure defaults."""
    if path:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Config file not found: {p}")
        return p
    env = os.environ.get("FLEX_CONFIG")
    if env:
        p = Path(env)
        if not p.exists():
            raise FileNotFoundError(f"$FLEX_CONFIG points to a missing file: {p}")
        return p
    local = Path.cwd() / "flex.toml"
    if local.exists():
        return local
    if ACTIVE_CONFIG.exists():
        return ACTIVE_CONFIG
    return None


def load_config(path: str | Path | None = None) -> FlexConfig:
    """Load the active configuration (see :func:`find_config`), or pure defaults."""
    found = find_config(path)
    if found is None:
        return FlexConfig()
    with open(found, "rb") as f:
        raw = tomllib.load(f)
    cfg = FlexConfig.model_validate(raw)
    cfg.source = found
    return cfg


def activate(manifest: str | Path, *, install: bool = True) -> FlexConfig:
    """Activate an ecosystem: install its packages and make it the active config."""
    manifest = Path(manifest)
    cfg = load_config(manifest)  # validates
    if install and cfg.ecosystem.packages:
        from flex.pkgmanager import PackageManager

        PackageManager().install(*cfg.ecosystem.packages)
    ACTIVE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    if manifest.resolve() != ACTIVE_CONFIG.resolve():
        ACTIVE_CONFIG.write_text(manifest.read_text(encoding="utf-8"), encoding="utf-8")
    get_logger("ecosystem").info("Ecosystem '%s' activated -> %s", cfg.ecosystem.name, ACTIVE_CONFIG)
    cfg.source = ACTIVE_CONFIG
    return cfg
