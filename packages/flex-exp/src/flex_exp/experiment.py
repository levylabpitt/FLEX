"""The default FLEX experiment handler."""

from __future__ import annotations

import getpass
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from flex.ecosystem import FlexConfig, load_config
from flex.instrument import Instrument
from flex.log import add_file_log, enable_console, get_logger, remove_log_handler
from flex.metadata import ExperimentRecord, NoteRecord


def new_id() -> str:
    """Sortable, collision-safe id: timestamp + 4 hex chars."""
    return datetime.now().strftime("%Y%m%d%H%M%S") + "-" + secrets.token_hex(2)


class Experiment:
    """An experiment session: instruments, measurements, notes, and records.

    Works with any FLEX instrument (VISA, TCP, serial, ZMQ, simulated) and
    builds its services — metadata store, storage backend, data writer, hooks —
    from the active ecosystem configuration. With no configuration, everything
    lands in SQLite + HDF5 files under the user data directory.

    Usage::

        with Experiment("jane") as exp:
            lockin = exp.add(SR7270, "lockin", "USB0::...")
            with exp.measurement("IV curve") as m:
                m.add_row(voltage=0.1, current=2.5e-9)
    """

    def __init__(
        self,
        user: str = "",
        *,
        name: str = "",
        notes: str = "",
        config: FlexConfig | str | Path | None = None,
        cell_log: bool = True,
    ):
        self.config = config if isinstance(config, FlexConfig) else load_config(config)
        self.id = new_id()
        self.user = user or getpass.getuser()
        self.name = name
        self.start_time = datetime.now()
        self.end_time: datetime | None = None
        self.instruments: dict[str, Instrument] = {}
        self._ended = False

        enable_console()
        log_path = Path(self.config.data.root) / self.id[:4] / self.id / "experiment.log"
        self._log_handler = add_file_log(log_path)
        self.log = get_logger("exp")

        self.storage = self.config.build_storage()
        self.events = self.config.build_bus()
        self.db = None
        try:
            self.db = self.config.build_db()
        except Exception as e:
            if self.config.exp.strict_metadata:
                raise
            self.log.warning("Metadata store unavailable (%s) - continuing without it", e)

        self._record(
            lambda db: db.record_experiment_start(
                ExperimentRecord(
                    id=self.id,
                    user=self.user,
                    name=self.name,
                    start_time=self.start_time,
                    config=self.config.model_dump(mode="json"),
                )
            )
        )
        self.events.emit("experiment.start", experiment=self)
        self.log.info("Experiment %s started (user: %s)", self.id, self.user)
        if notes:
            self.note(notes)

        self._cell_logger = None
        if cell_log:
            from flex_exp.celllog import CellLogger

            self._cell_logger = CellLogger.attach(self)

    # -- instruments -----------------------------------------------------

    def add_instrument(self, instrument: Instrument, name: str | None = None) -> Instrument:
        """Register an already-constructed instrument; it becomes ``exp.<name>``."""
        name = name or instrument.name
        if name in self.instruments:
            raise ValueError(f"An instrument named '{name}' is already registered")
        self.instruments[name] = instrument
        self.events.emit("instrument.added", experiment=self, instrument=instrument)
        self.log.info("Instrument added: %s (%s)", name, type(instrument).__name__)
        return instrument

    def add(self, cls: type, /, *args: Any, name: str | None = None, **kwargs: Any) -> Any:
        """Construct and register an instrument: ``exp.add(SR7270, "lockin", "USB0::...")``."""
        return self.add_instrument(cls(*args, **kwargs), name)

    def get(self, key: str | type) -> Instrument:
        """Look up an instrument by name, class, or capability protocol."""
        if isinstance(key, str):
            if key in self.instruments:
                return self.instruments[key]
            have = ", ".join(self.instruments) or "none"
            raise KeyError(f"No instrument '{key}' (registered: {have})")
        matches = [i for i in self.instruments.values() if isinstance(i, key)]
        if not matches:
            raise KeyError(f"No registered instrument provides {key.__name__}")
        if len(matches) > 1:
            names = ", ".join(i.name for i in matches)
            self.log.warning("%s provided by several instruments (%s); using '%s'",
                             key.__name__, names, matches[0].name)
        return matches[0]

    def __getattr__(self, name: str) -> Instrument:
        instruments = self.__dict__.get("instruments", {})
        if name in instruments:
            return instruments[name]
        raise AttributeError(f"'{type(self).__name__}' has no attribute or instrument '{name}'")

    def load_station(self, station: str | None = None) -> None:
        """Instantiate every instrument defined for a station in the config."""
        stations = self.config.stations
        if not stations:
            raise ValueError("No [stations.*] defined in the active configuration")
        if station is None:
            station = self.config.lab.station if self.config.lab.station in stations else None
            if station is None and len(stations) == 1:
                station = next(iter(stations))
            if station is None:
                raise ValueError(f"Choose a station: {', '.join(stations)}")
        from flex.pkgmanager import PackageManager

        manager = PackageManager()
        for name, spec in stations[station].instruments.items():
            cls = manager.resolve_driver(spec.driver)
            args = (spec.address,) if spec.address else ()
            self.add_instrument(cls(name, *args, **spec.options()), name)

    def close_all(self) -> None:
        """Close every registered instrument (errors logged, not raised)."""
        for name, instrument in list(self.instruments.items()):
            try:
                instrument.close()
                self.log.info("Closed: %s", name)
            except Exception as e:
                self.log.warning("%s.close() failed: %s", name, e)

    # -- measurements & notes ----------------------------------------------

    def measurement(self, name: str = "", *, notes: str = "", writer: str | None = None):
        """A new measurement context: ``with exp.measurement("IV") as m: ...``"""
        from flex_exp.measurement import Measurement

        return Measurement(self, name=name, notes=notes, writer=writer)

    def note(self, text: str, *, measurement_id: str | None = None) -> None:
        record = NoteRecord(
            experiment_id=self.id, text=text, measurement_id=measurement_id, time=datetime.now()
        )
        self._record(lambda db: db.record_note(record))
        self.events.emit("note.added", experiment=self, note=record)
        self.log.info("Note: %s", text)

    def snapshot(self, *, read: bool = True) -> dict[str, Any]:
        return {
            "experiment_id": self.id,
            "user": self.user,
            "name": self.name,
            "instruments": {n: i.snapshot(read=read) for n, i in self.instruments.items()},
        }

    # -- lifecycle ---------------------------------------------------------

    def end(self) -> None:
        """Finish the experiment: record end time, fire hooks, release services."""
        if self._ended:
            return
        self._ended = True
        self.end_time = datetime.now()
        if self._cell_logger:
            self._cell_logger.detach()
        self._record(
            lambda db: db.record_experiment_end(self.id, self.end_time, list(self.instruments))
        )
        self.events.emit("experiment.end", experiment=self)
        self.log.info("Experiment %s ended", self.id)
        if self.db is not None:
            try:
                self.db.close()
            except Exception:
                pass
        remove_log_handler(self._log_handler)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None and exc_type is not KeyboardInterrupt:
            self.log.error("Experiment aborted by %s: %s", exc_type.__name__, exc_val)
        self.end()
        self.close_all()

    def _record(self, action) -> None:
        """Run a metadata write; failures never interrupt the experiment
        (unless ``[exp] strict_metadata = true``)."""
        if self.db is None:
            return
        try:
            action(self.db)
        except Exception as e:
            if self.config.exp.strict_metadata:
                raise
            self.log.warning("Metadata write failed (%s) - continuing", e)

    def __repr__(self) -> str:
        return (
            f"Experiment(id='{self.id}', user='{self.user}', "
            f"instruments={list(self.instruments)})"
        )

    def _repr_html_(self) -> str:
        from flex.display import card, table

        rows = [
            [n, type(i).__name__, i.address or "—"] for n, i in self.instruments.items()
        ]
        sections = [("Instruments", table(["Name", "Driver", "Address"], rows))] if rows else []
        return card(
            "Experiment",
            {
                "ID": self.id,
                "User": self.user,
                "Name": self.name or "—",
                "Started": self.start_time.strftime("%Y-%m-%d %H:%M:%S"),
            },
            sections,
        )
