"""The default metadata store: a single SQLite file, zero setup."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from flex.data.storage import FilePointer
from flex.log import get_logger
from flex.metadata import (
    CellRecord,
    ExperimentRecord,
    InstrumentRecord,
    LogEntryRecord,
    MeasurementRecord,
    MetadataStore,
    NoteRecord,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS flex_experiments (
    id           TEXT PRIMARY KEY,
    user         TEXT NOT NULL,
    name         TEXT DEFAULT '',
    start_time   TEXT,
    end_time     TEXT,
    ecosystem    TEXT,
    station      TEXT,
    host         TEXT,
    flex_version TEXT,
    config       TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS flex_measurements (
    id            TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES flex_experiments(id),
    name          TEXT DEFAULT '',
    start_time    TEXT,
    end_time      TEXT,
    aborted       INTEGER DEFAULT 0,
    writer        TEXT,
    rows          INTEGER,
    file_uri      TEXT,
    file_backend  TEXT,
    file_size     INTEGER
);
CREATE TABLE IF NOT EXISTS flex_notes (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id  TEXT NOT NULL REFERENCES flex_experiments(id),
    measurement_id TEXT,
    time           TEXT,
    text           TEXT
);
CREATE TABLE IF NOT EXISTS flex_cells (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id   TEXT NOT NULL REFERENCES flex_experiments(id),
    time            TEXT,
    execution_count INTEGER,
    source          TEXT,
    success         INTEGER DEFAULT 1,
    error           TEXT
);
CREATE TABLE IF NOT EXISTS flex_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT NOT NULL REFERENCES flex_experiments(id),
    time          TEXT,
    level         TEXT,
    logger_name   TEXT,
    message       TEXT,
    exc_text      TEXT
);
CREATE TABLE IF NOT EXISTS flex_instruments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT NOT NULL REFERENCES flex_experiments(id),
    name          TEXT,
    driver        TEXT,
    address       TEXT,
    options       TEXT DEFAULT '{}',
    connected_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_flex_meas_exp ON flex_measurements(experiment_id);
CREATE INDEX IF NOT EXISTS idx_flex_notes_exp ON flex_notes(experiment_id);
CREATE INDEX IF NOT EXISTS idx_flex_cells_exp ON flex_cells(experiment_id);
CREATE INDEX IF NOT EXISTS idx_flex_logs_exp ON flex_logs(experiment_id);
CREATE INDEX IF NOT EXISTS idx_flex_instruments_exp ON flex_instruments(experiment_id);
"""


def _iso(t: datetime | None) -> str | None:
    return t.isoformat(sep=" ", timespec="seconds") if t else None


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


class SQLiteStore(MetadataStore):
    """Metadata in ``{data_root}/flex.db`` (or an explicit ``path``)."""

    def __init__(self, *, path: str | Path | None = None, data_root: str | Path | None = None, **_options: Any):
        if path is None:
            if data_root is None:
                from flex.ecosystem import default_data_root

                data_root = default_data_root()
            path = Path(data_root) / "flex.db"
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        get_logger("db.sqlite").debug("Open: %s", self.path)

    # -- writing ----------------------------------------------------------

    def record_experiment_start(self, record: ExperimentRecord, **extra: Any) -> None:
        self._conn.execute(
            "INSERT INTO flex_experiments"
            " (id, user, name, start_time, end_time, ecosystem, station, host, flex_version, config)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET user = excluded.user, name = excluded.name",
            (
                record.id,
                record.user,
                record.name,
                _iso(record.start_time),
                _iso(record.end_time),
                record.ecosystem,
                record.station,
                record.host,
                record.flex_version,
                json.dumps(record.config, default=str),
            ),
        )
        self._conn.commit()

    def record_experiment_end(self, experiment_id: str, end_time: datetime, **extra: Any) -> None:
        self._conn.execute(
            "UPDATE flex_experiments SET end_time = ? WHERE id = ?", (_iso(end_time), experiment_id)
        )
        self._conn.commit()

    def record_measurement_start(self, record: MeasurementRecord, **extra: Any) -> None:
        self._conn.execute(
            "INSERT INTO flex_measurements (id, experiment_id, name, start_time, end_time, aborted)"
            " VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
            (
                record.id,
                record.experiment_id,
                record.name,
                _iso(record.start_time),
                _iso(record.end_time),
                int(record.aborted),
            ),
        )
        self._conn.commit()

    def record_measurement_end(
        self,
        measurement_id: str,
        end_time: datetime,
        file: FilePointer | None,
        aborted: bool = False,
        *,
        writer: str | None = None,
        rows: int | None = None,
        **extra: Any,
    ) -> None:
        self._conn.execute(
            "UPDATE flex_measurements"
            " SET end_time = ?, file_uri = ?, file_backend = ?, file_size = ?, aborted = ?,"
            "     writer = ?, rows = ?"
            " WHERE id = ?",
            (
                _iso(end_time),
                file.uri if file else None,
                file.backend if file else None,
                file.size if file else None,
                int(aborted),
                writer,
                rows,
                measurement_id,
            ),
        )
        self._conn.commit()

    def record_note(self, record: NoteRecord, **extra: Any) -> None:
        self._conn.execute(
            "INSERT INTO flex_notes (experiment_id, measurement_id, time, text) VALUES (?, ?, ?, ?)",
            (record.experiment_id, record.measurement_id, _iso(record.time), record.text),
        )
        self._conn.commit()

    def record_cell(self, record: CellRecord, **extra: Any) -> None:
        self._conn.execute(
            "INSERT INTO flex_cells (experiment_id, time, execution_count, source, success, error)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                record.experiment_id,
                _iso(record.time),
                record.execution_count,
                record.source,
                int(record.success),
                record.error,
            ),
        )
        self._conn.commit()

    def record_log(self, record: LogEntryRecord, **extra: Any) -> None:
        self._conn.execute(
            "INSERT INTO flex_logs (experiment_id, time, level, logger_name, message, exc_text)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                record.experiment_id,
                _iso(record.time),
                record.level,
                record.logger_name,
                record.message,
                record.exc_text,
            ),
        )
        self._conn.commit()

    def record_instrument(self, record: InstrumentRecord, **extra: Any) -> None:
        self._conn.execute(
            "INSERT INTO flex_instruments (experiment_id, name, driver, address, options, connected_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                record.experiment_id,
                record.name,
                record.driver,
                record.address,
                json.dumps(record.options, default=str),
                _iso(record.connected_at),
            ),
        )
        self._conn.commit()

    # -- reading ----------------------------------------------------------

    def get_experiment(self, experiment_id: str) -> ExperimentRecord | None:
        row = self._conn.execute(
            "SELECT id, user, name, start_time, end_time, ecosystem, station, host, flex_version, config"
            " FROM flex_experiments WHERE id = ?",
            (experiment_id,),
        ).fetchone()
        return self._experiment(row) if row else None

    def list_experiments(self, *, user: str | None = None, limit: int = 50) -> list[ExperimentRecord]:
        sql = (
            "SELECT id, user, name, start_time, end_time, ecosystem, station, host, flex_version, config"
            " FROM flex_experiments"
        )
        params: tuple = ()
        if user:
            sql += " WHERE user = ?"
            params = (user,)
        sql += " ORDER BY start_time DESC LIMIT ?"
        rows = self._conn.execute(sql, (*params, limit)).fetchall()
        return [self._experiment(r) for r in rows]

    def list_measurements(self, experiment_id: str) -> list[MeasurementRecord]:
        rows = self._conn.execute(
            "SELECT id, experiment_id, name, start_time, end_time, aborted, writer, rows,"
            "        file_uri, file_backend, file_size"
            " FROM flex_measurements WHERE experiment_id = ? ORDER BY start_time",
            (experiment_id,),
        ).fetchall()
        return [
            MeasurementRecord(
                id=r[0],
                experiment_id=r[1],
                name=r[2],
                start_time=_dt(r[3]),
                end_time=_dt(r[4]),
                aborted=bool(r[5]),
                writer=r[6],
                rows=r[7],
                file=FilePointer(uri=r[8], backend=r[9] or "local", size=r[10]) if r[8] else None,
            )
            for r in rows
        ]

    def list_notes(self, experiment_id: str) -> list[NoteRecord]:
        rows = self._conn.execute(
            "SELECT experiment_id, measurement_id, time, text FROM flex_notes"
            " WHERE experiment_id = ? ORDER BY id",
            (experiment_id,),
        ).fetchall()
        return [
            NoteRecord(experiment_id=r[0], measurement_id=r[1], time=_dt(r[2]), text=r[3]) for r in rows
        ]

    def list_cells(self, experiment_id: str) -> list[CellRecord]:
        rows = self._conn.execute(
            "SELECT experiment_id, time, execution_count, source, success, error FROM flex_cells"
            " WHERE experiment_id = ? ORDER BY id",
            (experiment_id,),
        ).fetchall()
        return [
            CellRecord(
                experiment_id=r[0],
                time=_dt(r[1]),
                execution_count=r[2],
                source=r[3],
                success=bool(r[4]),
                error=r[5],
            )
            for r in rows
        ]

    def list_logs(self, experiment_id: str, *, level: str | None = None) -> list[LogEntryRecord]:
        sql = (
            "SELECT experiment_id, time, level, logger_name, message, exc_text FROM flex_logs"
            " WHERE experiment_id = ?"
        )
        params: tuple = (experiment_id,)
        if level:
            sql += " AND level = ?"
            params = (*params, level)
        sql += " ORDER BY id"
        rows = self._conn.execute(sql, params).fetchall()
        return [
            LogEntryRecord(
                experiment_id=r[0], time=_dt(r[1]), level=r[2], logger_name=r[3], message=r[4], exc_text=r[5]
            )
            for r in rows
        ]

    def list_instruments(self, experiment_id: str) -> list[InstrumentRecord]:
        rows = self._conn.execute(
            "SELECT experiment_id, name, driver, address, options, connected_at FROM flex_instruments"
            " WHERE experiment_id = ? ORDER BY id",
            (experiment_id,),
        ).fetchall()
        return [
            InstrumentRecord(
                experiment_id=r[0],
                name=r[1],
                driver=r[2],
                address=r[3],
                options=json.loads(r[4] or "{}"),
                connected_at=_dt(r[5]),
            )
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _experiment(row) -> ExperimentRecord:
        return ExperimentRecord(
            id=row[0],
            user=row[1],
            name=row[2],
            start_time=_dt(row[3]),
            end_time=_dt(row[4]),
            ecosystem=row[5],
            station=row[6],
            host=row[7],
            flex_version=row[8],
            config=json.loads(row[9] or "{}"),
        )
