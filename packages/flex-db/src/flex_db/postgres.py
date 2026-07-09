"""PostgreSQL metadata store (psycopg 3).

Creates the FLEX core schema (``experiments``, ``measurements``, ``notes``)
in the configured database. Configuration::

    [db]
    backend = "postgres"
    dsn = "postgresql://user@db.example.org/lab"

.. note::
    Migration of the pre-v2 LevyLab tables (``exp``, ``meas``, ``cell_log``)
    into this schema is a coordinated, one-off step to plan with the lab —
    this store intentionally does not touch those tables.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg

from flex.data.storage import FilePointer
from flex.log import get_logger
from flex.metadata import ExperimentRecord, MeasurementRecord, MetadataStore, NoteRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id          TEXT PRIMARY KEY,
    "user"      TEXT NOT NULL,
    name        TEXT DEFAULT '',
    start_time  TIMESTAMP,
    end_time    TIMESTAMP,
    instruments JSONB DEFAULT '[]',
    config      JSONB DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS measurements (
    id            TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES experiments(id),
    name          TEXT DEFAULT '',
    start_time    TIMESTAMP,
    end_time      TIMESTAMP,
    file_uri      TEXT,
    file_backend  TEXT,
    aborted       BOOLEAN DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS notes (
    id            BIGSERIAL PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    measurement_id TEXT,
    time          TIMESTAMP,
    kind          TEXT DEFAULT 'note',
    text          TEXT
);
CREATE INDEX IF NOT EXISTS idx_meas_exp ON measurements(experiment_id);
CREATE INDEX IF NOT EXISTS idx_notes_exp ON notes(experiment_id);
"""


class PostgresStore(MetadataStore):
    def __init__(self, *, dsn: str, data_root: str | Path | None = None, **_options: Any):
        self._conn = psycopg.connect(dsn, autocommit=True)
        with self._conn.cursor() as cur:
            cur.execute(_SCHEMA)
        get_logger("db.postgres").debug("Connected: %s", self._conn.info.host)

    # -- writing ----------------------------------------------------------

    def record_experiment_start(self, record: ExperimentRecord, **extra: Any) -> None:
        self._execute(
            """INSERT INTO experiments (id, "user", name, start_time, end_time, instruments, config)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET "user" = EXCLUDED."user", name = EXCLUDED.name""",
            (
                record.id,
                record.user,
                record.name,
                record.start_time,
                record.end_time,
                json.dumps(record.instruments),
                json.dumps(record.config, default=str),
            ),
        )

    def record_experiment_end(
        self, experiment_id: str, end_time: datetime, instruments: list[str], **extra: Any
    ) -> None:
        self._execute(
            "UPDATE experiments SET end_time = %s, instruments = %s WHERE id = %s",
            (end_time, json.dumps(instruments), experiment_id),
        )

    def record_measurement_start(self, record: MeasurementRecord, **extra: Any) -> None:
        self._execute(
            """INSERT INTO measurements (id, experiment_id, name, start_time, end_time, aborted)
               VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING""",
            (
                record.id,
                record.experiment_id,
                record.name,
                record.start_time,
                record.end_time,
                record.aborted,
            ),
        )

    def record_measurement_end(
        self,
        measurement_id: str,
        end_time: datetime,
        file: FilePointer | None,
        aborted: bool = False,
        **extra: Any,
    ) -> None:
        self._execute(
            "UPDATE measurements SET end_time = %s, file_uri = %s, file_backend = %s, aborted = %s"
            " WHERE id = %s",
            (
                end_time,
                file.uri if file else None,
                file.backend if file else None,
                aborted,
                measurement_id,
            ),
        )

    def record_note(self, record: NoteRecord, **extra: Any) -> None:
        self._execute(
            "INSERT INTO notes (experiment_id, measurement_id, time, kind, text)"
            " VALUES (%s, %s, %s, %s, %s)",
            (record.experiment_id, record.measurement_id, record.time, record.kind, record.text),
        )

    # -- reading ----------------------------------------------------------

    def get_experiment(self, experiment_id: str) -> ExperimentRecord | None:
        rows = self._query(
            'SELECT id, "user", name, start_time, end_time, instruments, config'
            " FROM experiments WHERE id = %s",
            (experiment_id,),
        )
        return self._experiment(rows[0]) if rows else None

    def list_experiments(self, *, user: str | None = None, limit: int = 50) -> list[ExperimentRecord]:
        sql = 'SELECT id, "user", name, start_time, end_time, instruments, config FROM experiments'
        params: tuple = ()
        if user:
            sql += ' WHERE "user" = %s'
            params = (user,)
        sql += " ORDER BY start_time DESC LIMIT %s"
        return [self._experiment(r) for r in self._query(sql, (*params, limit))]

    def list_measurements(self, experiment_id: str) -> list[MeasurementRecord]:
        rows = self._query(
            "SELECT id, experiment_id, name, start_time, end_time, file_uri, file_backend, aborted"
            " FROM measurements WHERE experiment_id = %s ORDER BY start_time",
            (experiment_id,),
        )
        return [
            MeasurementRecord(
                id=r[0],
                experiment_id=r[1],
                name=r[2],
                start_time=r[3],
                end_time=r[4],
                file=FilePointer(uri=r[5], backend=r[6] or "local") if r[5] else None,
                aborted=bool(r[7]),
            )
            for r in rows
        ]

    def list_notes(self, experiment_id: str) -> list[NoteRecord]:
        rows = self._query(
            "SELECT experiment_id, measurement_id, time, kind, text FROM notes"
            " WHERE experiment_id = %s ORDER BY id",
            (experiment_id,),
        )
        return [
            NoteRecord(experiment_id=r[0], measurement_id=r[1], time=r[2], kind=r[3], text=r[4])
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()

    # -- internals ---------------------------------------------------------

    def _execute(self, sql: str, params: tuple) -> None:
        with self._conn.cursor() as cur:
            cur.execute(sql, params)

    def _query(self, sql: str, params: tuple) -> list[tuple]:
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    @staticmethod
    def _experiment(row: tuple) -> ExperimentRecord:
        instruments = row[5] if isinstance(row[5], list) else json.loads(row[5] or "[]")
        config = row[6] if isinstance(row[6], dict) else json.loads(row[6] or "{}")
        return ExperimentRecord(
            id=row[0],
            user=row[1],
            name=row[2],
            start_time=row[3],
            end_time=row[4],
            instruments=instruments,
            config=config,
        )
