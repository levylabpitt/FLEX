import pytest

from flex.instrument import Enum, Numbers, SimulatedInstrument, capabilities


def test_command_parameters():
    sim = SimulatedInstrument("k2400", replies={"SOUR:VOLT?": "1.25"})
    voltage = sim.add_parameter(
        "voltage", get_cmd="SOUR:VOLT?", set_cmd="SOUR:VOLT {}", get_parser=float, unit="V"
    )
    assert voltage() == 1.25
    voltage(2.5)
    assert sim.sent == ["SOUR:VOLT?", "SOUR:VOLT 2.5"]
    assert voltage.full_name == "k2400.voltage"


def test_callable_parameters_and_sim_parameter():
    sim = SimulatedInstrument()
    gate = sim.add_sim_parameter("gate", initial=0.0, unit="V")
    gate(0.5)
    assert gate() == 0.5
    assert sim.sent == []  # no protocol traffic


def test_validators():
    sim = SimulatedInstrument()
    gate = sim.add_sim_parameter("gate", vals=Numbers(-1, 1))
    with pytest.raises(ValueError):
        gate(2.0)
    mode = sim.add_sim_parameter("mode", initial="Sine", vals=Enum("Sine", "Square"))
    with pytest.raises(ValueError):
        mode("Sawtooth")
    mode("Square")
    assert mode() == "Square"


def test_unreadable_unwritable_parameters():
    sim = SimulatedInstrument()
    write_only = sim.add_parameter("trigger", setter=lambda v: None)
    with pytest.raises(NotImplementedError):
        write_only()
    read_only = sim.add_parameter("status", getter=lambda: "ok")
    with pytest.raises(NotImplementedError):
        read_only("value")


def test_duplicate_parameter_rejected():
    sim = SimulatedInstrument()
    sim.add_sim_parameter("gate")
    with pytest.raises(ValueError, match="already has"):
        sim.add_sim_parameter("gate")


def test_snapshot():
    sim = SimulatedInstrument("lockin")
    sim.add_sim_parameter("frequency", initial=17.7, unit="Hz")

    def broken():
        raise RuntimeError("no comms")

    sim.add_parameter("temperature", getter=broken, unit="K")
    snap = sim.snapshot()
    assert snap["name"] == "lockin"
    assert snap["parameters"]["frequency"] == {"unit": "Hz", "value": 17.7}
    assert "no comms" in snap["parameters"]["temperature"]["error"]


def test_capability_conformance():
    class FakeCryostat(SimulatedInstrument):
        def get_temperature(self) -> float:
            return 4.2

        def set_temperature(self, setpoint, *, rate=None):
            pass

    cryo = FakeCryostat()
    assert isinstance(cryo, capabilities.Temperature)
    assert not isinstance(cryo, capabilities.Magnet)


def test_context_manager_and_reprs():
    with SimulatedInstrument("sim1") as sim:
        sim.add_sim_parameter("x", unit="V")
        assert "sim1" in repr(sim)
        html = sim._repr_html_()
        assert "sim1" in html and "flex-card" in html
