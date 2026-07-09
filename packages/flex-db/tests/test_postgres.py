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
        cur.execute("TRUNCATE notes, measurements, experiments")
    yield s
    s.close()


def test_lifecycle(store):
    from flex.data.storage import FilePointer
    from flex.metadata import ExperimentRecord, MeasurementRecord, NoteRecord

    t0, t1 = datetime(2026, 7, 9, 12), datetime(2026, 7, 9, 13)
    store.record_experiment_start(
        ExperimentRecord(id="e1", user="u", name="demo", start_time=t0, config={"a": 1})
    )
    store.record_measurement_start(MeasurementRecord(id="m1", experiment_id="e1", start_time=t0))
    store.record_measurement_end("m1", t1, FilePointer(uri="/data/m1.h5"), aborted=False)
    store.record_note(NoteRecord(experiment_id="e1", text="hello", time=t0))
    store.record_experiment_end("e1", t1, ["lockin"])

    exp = store.get_experiment("e1")
    assert exp.user == "u" and exp.end_time == t1 and exp.instruments == ["lockin"]
    (meas,) = store.list_measurements("e1")
    assert meas.file.uri == "/data/m1.h5"
    (note,) = store.list_notes("e1")
    assert note.text == "hello"
    assert [e.id for e in store.list_experiments(user="u")] == ["e1"]
