from datetime import datetime

from flex.data.storage import FilePointer
from flex.metadata import ExperimentRecord, MeasurementRecord, NoteRecord
from flex_db.sqlite import SQLiteStore

T0 = datetime(2026, 7, 9, 12, 0, 0)
T1 = datetime(2026, 7, 9, 13, 30, 0)


def make_store(tmp_path):
    return SQLiteStore(path=tmp_path / "flex.db")


def test_experiment_lifecycle(tmp_path):
    store = make_store(tmp_path)
    store.record_experiment_start(
        ExperimentRecord(id="e1", user="pubudu", name="gate sweep", start_time=T0, config={"db": "sqlite"})
    )
    store.record_experiment_end("e1", T1, ["lockin", "ppms"])

    exp = store.get_experiment("e1")
    assert exp.user == "pubudu"
    assert exp.name == "gate sweep"
    assert exp.start_time == T0
    assert exp.end_time == T1
    assert exp.instruments == ["lockin", "ppms"]
    assert exp.config == {"db": "sqlite"}
    store.close()


def test_measurements_and_notes(tmp_path):
    store = make_store(tmp_path)
    store.record_experiment_start(ExperimentRecord(id="e1", user="u", start_time=T0))
    store.record_measurement_start(
        MeasurementRecord(id="m1", experiment_id="e1", name="IV", start_time=T0)
    )
    store.record_measurement_end(
        "m1", T1, FilePointer(uri="C:/data/m1.h5", backend="local"), aborted=True
    )
    store.record_note(NoteRecord(experiment_id="e1", measurement_id="m1", text="contact 3 flaky", time=T0))

    (meas,) = store.list_measurements("e1")
    assert meas.name == "IV"
    assert meas.file.uri == "C:/data/m1.h5"
    assert meas.aborted

    (note,) = store.list_notes("e1")
    assert note.text == "contact 3 flaky"
    assert note.kind == "note"
    store.close()


def test_list_experiments_filter_and_order(tmp_path):
    store = make_store(tmp_path)
    for i, user in enumerate(["a", "b", "a"]):
        store.record_experiment_start(
            ExperimentRecord(id=f"e{i}", user=user, start_time=datetime(2026, 7, 9, 12, i))
        )
    assert [e.id for e in store.list_experiments()] == ["e2", "e1", "e0"]
    assert [e.id for e in store.list_experiments(user="a")] == ["e2", "e0"]
    assert len(store.list_experiments(limit=1)) == 1
    store.close()


def test_missing_experiment_is_none(tmp_path):
    store = make_store(tmp_path)
    assert store.get_experiment("nope") is None
    store.close()


def test_resolved_via_component_registry(tmp_path):
    """The ecosystem config must be able to build the sqlite backend by name."""
    from flex.ecosystem import FlexConfig

    cfg = FlexConfig.model_validate({"data": {"root": str(tmp_path)}})
    store = cfg.build_db()
    assert isinstance(store, SQLiteStore)
    assert store.path == tmp_path / "flex.db"
    store.close()
