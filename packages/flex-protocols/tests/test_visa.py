"""VISAInstrument tests with a fake pyvisa ResourceManager (no VISA runtime)."""

import pytest

import flex_protocols.visa as visa_module
from flex_protocols import VISAInstrument


class FakeResource:
    def __init__(self):
        self.written = []
        self.timeout = None
        self.closed = False

    def write(self, cmd):
        self.written.append(cmd)

    def query(self, cmd):
        self.written.append(cmd)
        if cmd == "*IDN?":
            return "Keithley,2400,1338477,C30\n"
        if cmd == "SOUR:VOLT?":
            return "0.75\n"
        return cmd

    def read(self):
        return "read-value\n"

    def close(self):
        self.closed = True


class FakeResourceManager:
    def __init__(self, *args):
        self.resource = FakeResource()

    def open_resource(self, resource, **kwargs):
        self.resource.timeout = kwargs.get("timeout")
        return self.resource


@pytest.fixture
def fake_visa(monkeypatch):
    monkeypatch.setattr(visa_module.pyvisa, "ResourceManager", FakeResourceManager)


def test_idn_parsing(fake_visa):
    inst = VISAInstrument("k2400", "GPIB0::24::INSTR")
    assert inst.idn() == {
        "vendor": "Keithley",
        "model": "2400",
        "serial": "1338477",
        "firmware": "C30",
    }


def test_query_write_parameters(fake_visa):
    inst = VISAInstrument("k2400", "GPIB0::24::INSTR", timeout=2.0)
    voltage = inst.add_parameter(
        "voltage", get_cmd="SOUR:VOLT?", set_cmd="SOUR:VOLT {}", get_parser=float, unit="V"
    )
    assert voltage() == 0.75
    voltage(1.5)
    assert inst._resource.written == ["SOUR:VOLT?", "SOUR:VOLT 1.5"]
    assert inst._resource.timeout == 2000


def test_close_is_idempotent(fake_visa):
    inst = VISAInstrument("k2400", "GPIB0::24::INSTR")
    resource = inst._resource
    inst.close()
    inst.close()
    assert resource.closed
