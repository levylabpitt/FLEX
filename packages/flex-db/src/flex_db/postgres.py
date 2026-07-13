"""PostgreSQL metadata store (psycopg 3).

Creates the FLEX core schema (``flex_experiments``, ``flex_measurements``,
``flex_notes``, ``flex_cells``, ``flex_logs``, ``flex_instruments``) in the
configured database. Configuration::

    [db]
    backend = "postgres"
    dsn = "postgresql://user@db.example.org/lab"

.. note::
    The pre-v2 LevyLab tables (``exp``, ``meas``, ``cell_log``) are a
    separate, coordinated migration to plan with the lab if ever needed —
    this store's ``flex_``-prefixed tables never touch them, so both can
    coexist in the same database.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg

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
    "user"       TEXT NOT NULL,
    name         TEXT DEFAULT '',
    start_time   TIMESTAMP,
    end_time     TIMESTAMP,
    ecosystem    TEXT,
    station      TEXT,
    host         TEXT,
    flex_version TEXT,
    config       JSONB DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS flex_measurements (
    id            TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES flex_experiments(id),
    name          TEXT DEFAULT '',
    start_time    TIMESTAMP,
    end_time      TIMESTAMP,
    aborted       BOOLEAN DEFAULT FALSE,
    writer        TEXT,
    rows          INTEGER,
    file_uri      TEXT,
    file_backend  TEXT,
    file_size     BIGINT
);
CREATE TABLE IF NOT EXISTS flex_notes (
    id             BIGSERIAL PRIMARY KEY,
    experiment_id  TEXT NOT NULL REFERENCES flex_experiments(id),
    measurement_id TEXT,
    time           TIMESTAMP,
    text           TEXT
);
CREATE TABLE IF NOT EXISTS flex_cells (
    id              BIGSERIAL PRIMARY KEY,
    experiment_id   TEXT NOT NULL REFERENCES flex_experiments(id),
    time            TIMESTAMP,
    execution_count INTEGER,
    source          TEXT,
    success         BOOLEAN DEFAULT TRUE,
    error           TEXT
);
CREATE TABLE IF NOT EXISTS flex_logs (
    id            BIGSERIAL PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES flex_experiments(id),
    time          TIMESTAMP,
    level         TEXT,
    logger_name   TEXT,
    message       TEXT,
    exc_text      TEXT
);
CREATE TABLE IF NOT EXISTS flex_instruments (
    id            BIGSERIAL PRIMARY KEY,
    experiment_id TEXT NOT NULL REFERENCES flex_experiments(id),
    name          TEXT,
    driver        TEXT,
    address       TEXT,
    options       JSONB DEFAULT '{}',
    connected_at  TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_flex_meas_exp ON flex_measurements(experiment_id);
CREATE INDEX IF NOT EXISTS idx_flex_notes_exp ON flex_notes(experiment_id);
CREATE INDEX IF NOT EXISTS idx_flex_cells_exp ON flex_cells(experiment_id);
CREATE INDEX IF NOT EXISTS idx_flex_logs_exp ON flex_logs(experiment_id);
CREATE INDEX IF NOT EXISTS idx_flex_instruments_exp ON flex_instruments(experiment_id);
"""


class PostgresStore(MetadataStore):
    def __init__(self, *, dsn: str, data_root: str | Path | None = None, **_options: Any):
        self._dsn = dsn
        self._conn = psycopg.connect(dsn, autocommit=True)
        with self._conn.cursor() as cur:
            cur.execute(_SCHEMA)
        get_logger("db.postgres").debug("Connected: %s", self._conn.info.host)

    # -- writing ----------------------------------------------------------

    def record_experiment_start(self, record: ExperimentRecord, **extra: Any) -> None:
        self._execute(
            """INSERT INTO flex_experiments
                   (id, "user", name, start_time, end_time, ecosystem, station, host, flex_version, config)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO UPDATE SET "user" = EXCLUDED."user", name = EXCLUDED.name""",
            (
                record.id,
                record.user,
                record.name,
                record.start_time,
                record.end_time,
                record.ecosystem,
                record.station,
                record.host,
                record.flex_version,
                json.dumps(record.config, default=str),
            ),
        )

    def record_experiment_end(self, experiment_id: str, end_time: datetime, **extra: Any) -> None:
        self._execute(
            "UPDATE flex_experiments SET end_time = %s WHERE id = %s", (end_time, experiment_id)
        )

    def record_measurement_start(self, record: MeasurementRecord, **extra: Any) -> None:
        self._execute(
            """INSERT INTO flex_measurements (id, experiment_id, name, start_time, end_time, aborted)
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
        *,
        writer: str | None = None,
        rows: int | None = None,
        **extra: Any,
    ) -> None:
        self._execute(
            "UPDATE flex_measurements"
            " SET end_time = %s, file_uri = %s, file_backend = %s, file_size = %s, aborted = %s,"
            "     writer = %s, rows = %s"
            " WHERE id = %s",
            (
                end_time,
                file.uri if file else None,
                file.backend if file else None,
                file.size if file else None,
                aborted,
                writer,
                rows,
                measurement_id,
            ),
        )

    def record_note(self, record: NoteRecord, **extra: Any) -> None:
        self._execute(
            "INSERT INTO flex_notes (experiment_id, measurement_id, time, text) VALUES (%s, %s, %s, %s)",
            (record.experiment_id, record.measurement_id, record.time, record.text),
        )

    def record_cell(self, record: CellRecord, **extra: Any) -> None:
        self._execute(
            "INSERT INTO flex_cells (experiment_id, time, execution_count, source, success, error)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (
                record.experiment_id,
                record.time,
                record.execution_count,
                record.source,
                record.success,
                record.error,
            ),
        )

    def record_log(self, record: LogEntryRecord, **extra: Any) -> None:
        self._execute(
            "INSERT INTO flex_logs (experiment_id, time, level, logger_name, message, exc_text)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (record.experiment_id, record.time, record.level, record.logger_name, record.message, record.exc_text),
        )

    def record_instrument(self, record: InstrumentRecord, **extra: Any) -> None:
        self._execute(
            "INSERT INTO flex_instruments (experiment_id, name, driver, address, options, connected_at)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (
                record.experiment_id,
                record.name,
                record.driver,
                record.address,
                json.dumps(record.options, default=str),
                record.connected_at,
            ),
        )

    # -- reading ----------------------------------------------------------

    def get_experiment(self, experiment_id: str) -> ExperimentRecord | None:
        rows = self._query(
            'SELECT id, "user", name, start_time, end_time, ecosystem, station, host, flex_version, config'
            " FROM flex_experiments WHERE id = %s",
            (experiment_id,),
        )
        return self._experiment(rows[0]) if rows else None

    def list_experiments(self, *, user: str | None = None, limit: int = 50) -> list[ExperimentRecord]:
        sql = (
            'SELECT id, "user", name, start_time, end_time, ecosystem, station, host, flex_version, config'
            " FROM flex_experiments"
        )
        params: tuple = ()
        if user:
            sql += ' WHERE "user" = %s'
            params = (user,)
        sql += " ORDER BY start_time DESC LIMIT %s"
        return [self._experiment(r) for r in self._query(sql, (*params, limit))]

    def list_measurements(self, experiment_id: str) -> list[MeasurementRecord]:
        rows = self._query(
            "SELECT id, experiment_id, name, start_time, end_time, aborted, writer, rows,"
            "        file_uri, file_backend, file_size"
            " FROM flex_measurements WHERE experiment_id = %s ORDER BY start_time",
            (experiment_id,),
        )
        return [
            MeasurementRecord(
                id=r[0],
                experiment_id=r[1],
                name=r[2],
                start_time=r[3],
                end_time=r[4],
                aborted=bool(r[5]),
                writer=r[6],
                rows=r[7],
                file=FilePointer(uri=r[8], backend=r[9] or "local", size=r[10]) if r[8] else None,
            )
            for r in rows
        ]

    def list_notes(self, experiment_id: str) -> list[NoteRecord]:
        rows = self._query(
            "SELECT experiment_id, measurement_id, time, text FROM flex_notes"
            " WHERE experiment_id = %s ORDER BY id",
            (experiment_id,),
        )
        return [
            NoteRecord(experiment_id=r[0], measurement_id=r[1], time=r[2], text=r[3]) for r in rows
        ]

    def list_cells(self, experiment_id: str) -> list[CellRecord]:
        rows = self._query(
            "SELECT experiment_id, time, execution_count, source, success, error FROM flex_cells"
            " WHERE experiment_id = %s ORDER BY id",
            (experiment_id,),
        )
        return [
            CellRecord(
                experiment_id=r[0],
                time=r[1],
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
            " WHERE experiment_id = %s"
        )
        params: tuple = (experiment_id,)
        if level:
            sql += " AND level = %s"
            params = (*params, level)
        sql += " ORDER BY id"
        rows = self._query(sql, params)
        return [
            LogEntryRecord(
                experiment_id=r[0], time=r[1], level=r[2], logger_name=r[3], message=r[4], exc_text=r[5]
            )
            for r in rows
        ]

    def list_instruments(self, experiment_id: str) -> list[InstrumentRecord]:
        rows = self._query(
            "SELECT experiment_id, name, driver, address, options, connected_at FROM flex_instruments"
            " WHERE experiment_id = %s ORDER BY id",
            (experiment_id,),
        )
        return [
            InstrumentRecord(
                experiment_id=r[0],
                name=r[1],
                driver=r[2],
                address=r[3],
                options=r[4] if isinstance(r[4], dict) else json.loads(r[4] or "{}"),
                connected_at=r[5],
            )
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()

    # -- internals ---------------------------------------------------------

    def _execute(self, sql: str, params: tuple) -> None:
        try:
            with self._conn.cursor() as cur:
                cur.execute(sql, params)
        except psycopg.OperationalError:
            self._conn = psycopg.connect(self._dsn, autocommit=True)
            with self._conn.cursor() as cur:
                cur.execute(sql, params)

    def _query(self, sql: str, params: tuple) -> list[tuple]:
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    @staticmethod
    def _experiment(row: tuple) -> ExperimentRecord:
        config = row[9] if isinstance(row[9], dict) else json.loads(row[9] or "{}")
        return ExperimentRecord(
            id=row[0],
            user=row[1],
            name=row[2],
            start_time=row[3],
            end_time=row[4],
            ecosystem=row[5],
            station=row[6],
            host=row[7],
            flex_version=row[8],
            config=config,
        )
