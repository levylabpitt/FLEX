import h5py
import numpy as np
import pytest

from flex.instrument import SimulatedInstrument
from flex_exp import Experiment, Scan, sweep


@pytest.fixture
def exp(config):
    with Experiment("u", config=config) as experiment:
        yield experiment


@pytest.fixture
def sim(exp):
    instrument = exp.add(SimulatedInstrument, "sim")
    instrument.add_sim_parameter("gate", unit="V")
    instrument.add_sim_parameter("x", initial=0.5, unit="V")
    return instrument


def test_single_axis_scan(exp, sim):
    gate = sim.parameters["gate"]
    values = np.linspace(0, 1, 11)
    m = Scan(sweep(gate, values)).measure(sim.parameters["x"]).run(exp, name="gate sweep", progress=False)

    assert m.rows == 11
    with h5py.File(m.file.uri) as f:
        np.testing.assert_allclose(f["data/sim.gate"][:], values)
        assert f["data/sim.gate"].attrs["unit"] == "V"
        np.testing.assert_allclose(f["data/sim.x"][:], 0.5)
    assert sim.values["gate"] == 1.0  # actually swept


def test_nested_scan_grid(exp, sim):
    outer = sim.add_sim_parameter("field", unit="T")
    gate = sim.parameters["gate"]
    m = (
        Scan(sweep(outer, [0.0, 1.0]), sweep(gate, [0.0, 0.5, 1.0]))
        .measure(sim.parameters["x"])
        .run(exp, progress=False)
    )
    assert m.rows == 6
    with h5py.File(m.file.uri) as f:
        np.testing.assert_allclose(f["data/sim.field"][:], [0, 0, 0, 1, 1, 1])
        np.testing.assert_allclose(f["data/sim.gate"][:], [0, 0.5, 1] * 2)


def test_measure_named_callables_and_each(exp, sim):
    gate = sim.parameters["gate"]
    seen = []
    m = (
        Scan(sweep(gate, [0.0, 1.0]))
        .measure(noise=lambda: 42.0)
        .each(seen.append)
        .run(exp, progress=False)
    )
    assert m.rows == 2
    assert [p["noise"] for p in seen] == [42.0, 42.0]


def test_abort_runs_cleanup_and_marks_aborted(exp, sim, tmp_path):
    gate = sim.parameters["gate"]
    cleanups = []

    def explode():
        if sim.values["gate"] >= 0.5:
            raise KeyboardInterrupt

    scan = (
        Scan(sweep(gate, [0.0, 0.5, 1.0], after=lambda: cleanups.append("axis")))
        .measure(reader=lambda: explode() or 0.0)
        .on_abort(lambda: cleanups.append("abort"))
    )
    with pytest.raises(KeyboardInterrupt):
        scan.run(exp, name="unsafe", progress=False)

    assert "abort" in cleanups and "axis" in cleanups

    from flex_db.sqlite import SQLiteStore

    store = SQLiteStore(path=tmp_path / "flex.db")
    (meas,) = store.list_measurements(exp.id)
    assert meas.aborted
    assert meas.file is not None  # data up to the abort is preserved
    store.close()


def test_sweep_callable_target(exp):
    calls = []
    m = Scan(sweep(calls.append, [1, 2, 3], name="step")).measure(v=lambda: 0.0).run(
        exp, progress=False
    )
    assert calls == [1, 2, 3]
    assert m.rows == 3
