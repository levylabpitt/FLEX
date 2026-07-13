from datetime import datetime

from flex.data.storage import FilePointer
from flex.metadata import (
    CellRecord,
    ExperimentRecord,
    InstrumentRecord,
    LogEntryRecord,
    MeasurementRecord,
    NoteRecord,
)
from flex_db.sqlite import SQLiteStore

T0 = datetime(2026, 7, 9, 12, 0, 0)
T1 = datetime(2026, 7, 9, 13, 30, 0)


def make_store(tmp_path):
    return SQLiteStore(path=tmp_path / "flex.db")


def test_experiment_lifecycle(tmp_path):
    store = make_store(tmp_path)
    store.record_experiment_start(
        ExperimentRecord(
            id="e1", user="pubudu", name="gate sweep", start_time=T0,
            ecosystem="levylab", station="cryo1", host="bench-pc", flex_version="2.0.0a1",
            config={"db": "sqlite"},
        )
    )
    store.record_experiment_end("e1", T1)

    exp = store.get_experiment("e1")
    assert exp.user == "pubudu"
    assert exp.name == "gate sweep"
    assert exp.start_time == T0
    assert exp.end_time == T1
    assert exp.ecosystem == "levylab"
    assert exp.station == "cryo1"
    assert exp.host == "bench-pc"
    assert exp.flex_version == "2.0.0a1"
    assert exp.config == {"db": "sqlite"}
    store.close()


def test_measurements_and_notes(tmp_path):
    store = make_store(tmp_path)
    store.record_experiment_start(ExperimentRecord(id="e1", user="u", start_time=T0))
    store.record_measurement_start(
        MeasurementRecord(id="m1", experiment_id="e1", name="IV", start_time=T0)
    )
    store.record_measurement_end(
        "m1", T1, FilePointer(uri="C:/data/m1.h5", backend="local", size=1024),
        aborted=True, writer="hdf5", rows=5,
    )
    store.record_note(NoteRecord(experiment_id="e1", measurement_id="m1", text="contact 3 flaky", time=T0))

    (meas,) = store.list_measurements("e1")
    assert meas.name == "IV"
    assert meas.file.uri == "C:/data/m1.h5"
    assert meas.file.size == 1024
    assert meas.aborted
    assert meas.writer == "hdf5"
    assert meas.rows == 5

    (note,) = store.list_notes("e1")
    assert note.text == "contact 3 flaky"
    store.close()


def test_cells_logs_and_instruments(tmp_path):
    store = make_store(tmp_path)
    store.record_experiment_start(ExperimentRecord(id="e1", user="u", start_time=T0))

    store.record_cell(
        CellRecord(experiment_id="e1", source="gate(0.5)", time=T0, execution_count=3, success=True)
    )
    store.record_cell(
        CellRecord(
            experiment_id="e1", source="1/0", time=T1, execution_count=4,
            success=False, error="ZeroDivisionError",
        )
    )
    (ok, bad) = store.list_cells("e1")
    assert ok.source == "gate(0.5)" and ok.success
    assert bad.error == "ZeroDivisionError" and not bad.success

    store.record_log(
        LogEntryRecord(
            experiment_id="e1", level="WARNING", logger_name="flex.inst.lockin",
            message="timeout", time=T0,
        )
    )
    store.record_log(
        LogEntryRecord(experiment_id="e1", level="ERROR", logger_name="flex.exp", message="boom", time=T1)
    )
    assert len(store.list_logs("e1")) == 2
    (error,) = store.list_logs("e1", level="ERROR")
    assert error.message == "boom"

    store.record_instrument(
        InstrumentRecord(
            experiment_id="e1", name="lockin", driver="flex_drivers.levylab.lockin:Lockin",
            address="tcp://localhost:29170", options={"unit": "V"}, connected_at=T0,
        )
    )
    (inst,) = store.list_instruments("e1")
    assert inst.name == "lockin"
    assert inst.driver == "flex_drivers.levylab.lockin:Lockin"
    assert inst.options == {"unit": "V"}
    store.close()


def test_replayed_starts_do_not_clobber_ends(tmp_path):
    store = make_store(tmp_path)
    store.record_experiment_start(ExperimentRecord(id="e1", user="u", start_time=T0))
    store.record_measurement_start(
        MeasurementRecord(id="m1", experiment_id="e1", name="IV", start_time=T0)
    )
    store.record_experiment_end("e1", T1)
    store.record_measurement_end("m1", T1, FilePointer(uri="C:/data/m1.h5", backend="local"))

    store.record_experiment_start(ExperimentRecord(id="e1", user="u2", start_time=T0))
    store.record_measurement_start(
        MeasurementRecord(id="m1", experiment_id="e1", name="IV", start_time=T0)
    )

    exp = store.get_experiment("e1")
    assert exp.user == "u2"
    assert exp.end_time == T1
    (meas,) = store.list_measurements("e1")
    assert meas.end_time == T1
    assert meas.file.uri == "C:/data/m1.h5"
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
