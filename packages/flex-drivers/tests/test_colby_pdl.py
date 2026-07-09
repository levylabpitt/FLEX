"""ColbyPDL tests with a fake pyvisa ResourceManager (no VISA runtime)."""

import pytest

import flex_drivers.colby.pdl as pdl_module
import flex_protocols.visa as visa_module
from flex_drivers.colby import ColbyPDL


class FakeResource:
    def __init__(self):
        self.written = []
        self.replies = {"RATE?": "700\r\n", "DEL?": "20.000 NS\r\n"}
        self.timeout = None
        self.closed = False

    def write(self, cmd):
        self.written.append(cmd)

    def query(self, cmd):
        self.written.append(cmd)
        return self.replies.get(cmd, "")

    def close(self):
        self.closed = True


class FakeResourceManager:
    def __init__(self, *args):
        self.resource = FakeResource()

    def open_resource(self, resource, **kwargs):
        self.resource.timeout = kwargs.get("timeout")
        return self.resource


@pytest.fixture
def pdl(monkeypatch):
    monkeypatch.setattr(visa_module.pyvisa, "ResourceManager", FakeResourceManager)
    monkeypatch.setattr(pdl_module.time, "sleep", lambda s: None)
    return ColbyPDL(resource="GPIB1::15::INSTR")


def test_reads_stepper_rate_on_connect(pdl):
    assert pdl._stepper_rate == "700"
    assert pdl._resource.written == ["RATE?"]


def test_set_delay_reuses_stored_rate(pdl):
    pdl.set_delay(20)
    assert pdl._resource.written == ["RATE?", "RATE 700", "DEL 20 ns"]


def test_set_delay_with_explicit_rate_and_unit(pdl):
    pdl.set_delay(1.5, unit="ps", stepper_rate=550)
    assert pdl._resource.written[-2:] == ["RATE 550", "DEL 1.5 ps"]
    assert pdl._stepper_rate == 550  # remembered for the next call


def test_get_delay(pdl):
    assert pdl.get_delay() == "20.000 NS"
    assert pdl.parameters["delay"].get() == "20.000 NS"
