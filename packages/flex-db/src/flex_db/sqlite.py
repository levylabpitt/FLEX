"""The default metadata store: a single SQLite file, zero setup."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from flex.data.storage import FilePointer
from flex.log import get_logger
from flex.metadata import ExperimentRecord, MeasurementRecord, MetadataStore, NoteRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id          TEXT PRIMARY KEY,
    user        TEXT NOT NULL,
    name        TEXT DEFAULT '',
    start_time  TEXT,
    end_time    TEXT,
    instruments TEXT DEFAULT '[]',
    config      TEXT DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS measurements (
    id            TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiments(id),
    name          TEXT DEFAULT '',
    start_time    TEXT,
    end_time      TEXT,
    file_uri      TEXT,
    file_backend  TEXT,
    aborted       INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS notes (
    rowid         INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id TEXT NOT NULL,
    measurement_id TEXT,
    time          TEXT,
    kind          TEXT DEFAULT 'note',
    text          TEXT
);
CREATE INDEX IF NOT EXISTS idx_meas_exp ON measurements(experiment_id);
CREATE INDEX IF NOT EXISTS idx_notes_exp ON notes(experiment_id);
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
            "INSERT INTO experiments (id, user, name, start_time, end_time, instruments, config)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET user = excluded.user, name = excluded.name",
            (
                record.id,
                record.user,
                record.name,
                _iso(record.start_time),
                _iso(record.end_time),
                json.dumps(record.instruments),
                json.dumps(record.config, default=str),
            ),
        )
        self._conn.commit()

    def record_experiment_end(
        self, experiment_id: str, end_time: datetime, instruments: list[str], **extra: Any
    ) -> None:
        self._conn.execute(
            "UPDATE experiments SET end_time = ?, instruments = ? WHERE id = ?",
            (_iso(end_time), json.dumps(instruments), experiment_id),
        )
        self._conn.commit()

    def record_measurement_start(self, record: MeasurementRecord, **extra: Any) -> None:
        self._conn.execute(
            "INSERT INTO measurements (id, experiment_id, name, start_time, end_time, aborted)"
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
        **extra: Any,
    ) -> None:
        self._conn.execute(
            "UPDATE measurements SET end_time = ?, file_uri = ?, file_backend = ?, aborted = ? WHERE id = ?",
            (
                _iso(end_time),
                file.uri if file else None,
                file.backend if file else None,
                int(aborted),
                measurement_id,
            ),
        )
        self._conn.commit()

    def record_note(self, record: NoteRecord, **extra: Any) -> None:
        self._conn.execute(
            "INSERT INTO notes (experiment_id, measurement_id, time, kind, text) VALUES (?, ?, ?, ?, ?)",
            (record.experiment_id, record.measurement_id, _iso(record.time), record.kind, record.text),
        )
        self._conn.commit()

    # -- reading ----------------------------------------------------------

    def get_experiment(self, experiment_id: str) -> ExperimentRecord | None:
        row = self._conn.execute(
            "SELECT id, user, name, start_time, end_time, instruments, config FROM experiments WHERE id = ?",
            (experiment_id,),
        ).fetchone()
        return self._experiment(row) if row else None

    def list_experiments(self, *, user: str | None = None, limit: int = 50) -> list[ExperimentRecord]:
        sql = "SELECT id, user, name, start_time, end_time, instruments, config FROM experiments"
        params: tuple = ()
        if user:
            sql += " WHERE user = ?"
            params = (user,)
        sql += " ORDER BY start_time DESC LIMIT ?"
        rows = self._conn.execute(sql, (*params, limit)).fetchall()
        return [self._experiment(r) for r in rows]

    def list_measurements(self, experiment_id: str) -> list[MeasurementRecord]:
        rows = self._conn.execute(
            "SELECT id, experiment_id, name, start_time, end_time, file_uri, file_backend, aborted"
            " FROM measurements WHERE experiment_id = ? ORDER BY start_time",
            (experiment_id,),
        ).fetchall()
        return [
            MeasurementRecord(
                id=r[0],
                experiment_id=r[1],
                name=r[2],
                start_time=_dt(r[3]),
                end_time=_dt(r[4]),
                file=FilePointer(uri=r[5], backend=r[6] or "local") if r[5] else None,
                aborted=bool(r[7]),
            )
            for r in rows
        ]

    def list_notes(self, experiment_id: str) -> list[NoteRecord]:
        rows = self._conn.execute(
            "SELECT experiment_id, measurement_id, time, kind, text FROM notes"
            " WHERE experiment_id = ? ORDER BY rowid",
            (experiment_id,),
        ).fetchall()
        return [
            NoteRecord(experiment_id=r[0], measurement_id=r[1], time=_dt(r[2]), kind=r[3], text=r[4])
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
            instruments=json.loads(row[5] or "[]"),
            config=json.loads(row[6] or "{}"),
        )
