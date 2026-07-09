"""One measurement = one data file + one metadata record."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

import numpy as np

from flex.data import ColumnSpec, FilePointer
from flex.instrument import Parameter
from flex.metadata import MeasurementRecord

if TYPE_CHECKING:
    from flex_exp.experiment import Experiment


class Measurement:
    """Context manager owning one measurement's data file.

    Two styles, freely mixed:

    * push rows yourself::

        with exp.measurement("IV") as m:
            m.add_row(voltage=v, current=i)

    * register parameters, then read them per point::

        with exp.measurement("gate sweep") as m:
            m.register(lockin.x, lockin.y)
            m.read_point(gate=0.1)      # reads registered params, records the row

    On exit the file is finalized (uploaded, if the storage backend is remote)
    and the metadata record updated — including an ``aborted`` flag if the
    block was left through an exception.
    """

    def __init__(
        self,
        experiment: Experiment,
        name: str = "",
        *,
        notes: str = "",
        writer: str | None = None,
    ):
        from flex_exp.experiment import new_id

        self.experiment = experiment
        self.name = name
        self.id = new_id()
        self.rows = 0
        self.file: FilePointer | None = None
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None
        self._notes_pending = notes
        self._writer = experiment.config.build_writer(writer)
        self._specs: list[tuple[str, Callable[[], Any] | None, str]] = []
        self._declared = False
        self._path = None

    # -- declaring what gets recorded ------------------------------------

    def register(self, *parameters: Parameter, **named: Parameter | Callable[[], Any]) -> Measurement:
        """Declare quantities read on every :meth:`read_point`.

        Positional arguments must be :class:`Parameter` (column name and unit
        come from the parameter). Keyword arguments name the column explicitly
        and may be a Parameter or any zero-argument callable.
        """
        if self._declared:
            raise RuntimeError("register() must be called before the first data point")
        for p in parameters:
            if not isinstance(p, Parameter):
                raise TypeError(f"register() positional args must be Parameters, got {p!r}; "
                                "use a keyword argument for plain callables")
            self._specs.append((p.full_name, p.get, p.unit))
        for key, v in named.items():
            if isinstance(v, Parameter):
                self._specs.append((key, v.get, v.unit))
            elif callable(v):
                self._specs.append((key, v, ""))
            else:
                raise TypeError(f"'{key}' must be a Parameter or callable, got {v!r}")
        return self

    def declare(self, name: str, unit: str = "") -> None:
        """Declare a column that is supplied per row (e.g. a sweep setpoint)."""
        if self._declared:
            raise RuntimeError("declare() must be called before the first data point")
        self._specs.append((name, None, unit))

    # -- recording data ------------------------------------------------------

    def add_row(self, **values: Any) -> None:
        """Append one data point. Columns are fixed by the first row."""
        if not self._declared:
            self._declare_columns(values.keys())
        self._writer.append(values)
        self.rows += 1

    def read_point(self, **setpoints: Any) -> dict[str, Any]:
        """Read every registered parameter, merge ``setpoints``, record the row."""
        values = {name: getter() for name, getter, _ in self._specs if getter is not None}
        values.update(setpoints)
        self.add_row(**values)
        return values

    def add_array(self, name: str, data: np.ndarray, *, attrs: dict[str, Any] | None = None) -> None:
        """Store a named free-form array (spectrum, waveform, image)."""
        self._writer.write_array(name, data, attrs=attrs)

    def add_note(self, text: str) -> None:
        self.experiment.note(text, measurement_id=self.id)

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> Measurement:
        exp = self.experiment
        self.start_time = datetime.now()
        self._path = exp.storage.new_measurement_path(exp.id, self.id, self._writer.suffix)
        self._writer.open(
            self._path,
            metadata={
                "experiment_id": exp.id,
                "measurement_id": self.id,
                "name": self.name,
                "user": exp.user,
                "start_time": self.start_time.isoformat(sep=" ", timespec="seconds"),
                "snapshot": exp.snapshot(),
            },
        )
        exp._record(
            lambda db: db.record_measurement_start(
                MeasurementRecord(
                    id=self.id, experiment_id=exp.id, name=self.name, start_time=self.start_time
                )
            )
        )
        exp.events.emit("measurement.start", experiment=exp, measurement=self)
        exp.log.info("Measurement %s started%s", self.id, f" ({self.name})" if self.name else "")
        if self._notes_pending:
            self.add_note(self._notes_pending)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        exp = self.experiment
        aborted = exc_type is not None
        self.end_time = datetime.now()
        try:
            self._writer.close()
        finally:
            try:
                self.file = exp.storage.finalize(self._path)
            except Exception as e:
                exp.log.error("Storage finalize failed (%s); file remains at %s", e, self._path)
                self.file = FilePointer(uri=str(self._path), backend="local")
        exp._record(
            lambda db: db.record_measurement_end(self.id, self.end_time, self.file, aborted)
        )
        exp.events.emit(
            "measurement.abort" if aborted else "measurement.end", experiment=exp, measurement=self
        )
        status = "ABORTED" if aborted else "done"
        exp.log.info("Measurement %s %s: %d rows -> %s", self.id, status, self.rows, self.file.uri)
        return False

    def _declare_columns(self, first_row_keys) -> None:
        columns = [ColumnSpec(name, unit) for name, _, unit in self._specs]
        known = {c.name for c in columns}
        columns += [ColumnSpec(k) for k in first_row_keys if k not in known]
        names = [c.name for c in columns]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise ValueError(f"Duplicate column name(s): {', '.join(sorted(duplicates))}")
        self._writer.add_columns(columns)
        self._declared = True

    def __repr__(self) -> str:
        return f"Measurement(id='{self.id}', name='{self.name}', rows={self.rows})"
