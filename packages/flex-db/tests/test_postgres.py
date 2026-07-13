"""PostgresStore integration tests.

These run only when a test database is available. Point FLEX_TEST_POSTGRES_DSN
at a disposable database, e.g.::

    set FLEX_TEST_POSTGRES_DSN=postgresql://postgres:postgres@localhost:5432/flex_test
"""

import os
from datetime import datetime

import pytest

DSN = os.environ.get("FLEX_TEST_POSTGRES_DSN")

pytestmark = pytest.mark.skipif(not DSN, reason="FLEX_TEST_POSTGRES_DSN not set")


@pytest.fixture
def store():
    from flex_db.postgres import PostgresStore

    s = PostgresStore(dsn=DSN)
    with s._conn.cursor() as cur:
        cur.execute(
            "TRUNCATE flex_notes, flex_cells, flex_logs, flex_instruments,"
            " flex_measurements, flex_experiments"
        )
    yield s
    s.close()


def test_lifecycle(store):
    from flex.data.storage import FilePointer
    from flex.metadata import (
        CellRecord,
        ExperimentRecord,
        InstrumentRecord,
        LogEntryRecord,
        MeasurementRecord,
        NoteRecord,
    )

    t0, t1 = datetime(2026, 7, 9, 12), datetime(2026, 7, 9, 13)
    store.record_experiment_start(
        ExperimentRecord(id="e1", user="u", name="demo", start_time=t0, ecosystem="levylab", config={"a": 1})
    )
    store.record_measurement_start(MeasurementRecord(id="m1", experiment_id="e1", start_time=t0))
    store.record_measurement_end(
        "m1", t1, FilePointer(uri="/data/m1.h5", size=42), aborted=False, writer="hdf5", rows=3
    )
    store.record_note(NoteRecord(experiment_id="e1", text="hello", time=t0))
    store.record_cell(CellRecord(experiment_id="e1", source="x = 1", time=t0, execution_count=1))
    store.record_log(
        LogEntryRecord(experiment_id="e1", level="WARNING", logger_name="flex.exp", message="hmm", time=t0)
    )
    store.record_instrument(
        InstrumentRecord(experiment_id="e1", name="lockin", driver="pkg:Lockin", connected_at=t0)
    )
    store.record_experiment_end("e1", t1)

    exp = store.get_experiment("e1")
    assert exp.user == "u" and exp.end_time == t1 and exp.ecosystem == "levylab"
    (meas,) = store.list_measurements("e1")
    assert meas.file.uri == "/data/m1.h5" and meas.file.size == 42 and meas.rows == 3
    (note,) = store.list_notes("e1")
    assert note.text == "hello"
    (cell,) = store.list_cells("e1")
    assert cell.source == "x = 1"
    (log,) = store.list_logs("e1")
    assert log.message == "hmm"
    (inst,) = store.list_instruments("e1")
    assert inst.name == "lockin"
    assert [e.id for e in store.list_experiments(user="u")] == ["e1"]
