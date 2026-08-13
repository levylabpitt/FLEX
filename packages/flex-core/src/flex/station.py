"""A Station: the set of instruments wired to this PC, from flex.toml.

Notebook use::

    station = Station.load()        # builds every [instruments.*] entry
    station.lockin.set_ao_dc(1, 0.5)

Server use: ``flex serve`` hosts a Station over ZMQ (see flex.server).
"""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

from flex.config import FlexConfig, load_config
from flex.events import EventBus
from flex.instrument import Instrument
from flex.log import get_logger


class Station:
    """A named collection of instruments sharing one event bus."""

    def __init__(self, instruments: dict[str, Instrument] | None = None, *,
                 name: str = "", config: FlexConfig | None = None):
        self.config = config or FlexConfig()
        self.name = name or self.config.lab.station or socket.gethostname()
        self.events = EventBus()
        self.instruments: dict[str, Instrument] = {}
        self.log = get_logger(f"station.{self.name}")
        for inst_name, inst in (instruments or {}).items():
            self.add_instrument(inst, inst_name)

    @classmethod
    def load(cls, config: FlexConfig | str | Path | None = None, *names: str) -> Station:
        """Build a Station from the active config's [instruments.*] entries
        (all of them, or just the given names)."""
        cfg = config if isinstance(config, FlexConfig) else load_config(config)
        configured = cfg.instruments
        if not configured:
            raise ValueError("No [instruments.*] defined in the active configuration")
        unknown = [n for n in names if n not in configured]
        if unknown:
            raise KeyError(
                f"Not in the configuration: {', '.join(unknown)}"
                f" (configured: {', '.join(configured)})"
            )
        station = cls(config=cfg)
        for name in names or configured:
            station.add_instrument(configured[name].build(name), name)
        return station

    def add_instrument(self, instrument: Instrument, name: str | None = None) -> Instrument:
        name = name or instrument.name
        if name in self.instruments:
            raise ValueError(f"Station already has an instrument '{name}'")
        self.instruments[name] = instrument
        instrument.events = self.events
        self.log.info("Instrument added: %s (%s)", name, type(instrument).__name__)
        return instrument

    def get(self, name: str) -> Instrument:
        if name not in self.instruments:
            have = ", ".join(self.instruments) or "none"
            raise KeyError(f"No instrument '{name}' (loaded: {have})")
        return self.instruments[name]

    def snapshot(self, *, read: bool = False) -> dict[str, Any]:
        return {name: inst.snapshot(read=read) for name, inst in self.instruments.items()}

    def close(self) -> None:
        for name, inst in self.instruments.items():
            try:
                inst.close()
            except Exception as e:
                self.log.warning("%s.close() failed: %s", name, e)

    def __getattr__(self, name: str) -> Instrument:
        instruments = self.__dict__.get("instruments", {})
        if name in instruments:
            return instruments[name]
        raise AttributeError(f"Station has no attribute or instrument '{name}'")

    def __dir__(self) -> list[str]:
        return [*super().__dir__(), *self.__dict__.get("instruments", {})]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __repr__(self) -> str:
        return f"<Station '{self.name}': {', '.join(self.instruments) or 'empty'}>"
