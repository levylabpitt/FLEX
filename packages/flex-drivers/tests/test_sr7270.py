"""SR7270 tests with a fake raw-USB pyvisa resource (no VISA runtime)."""

import pytest

import flex_protocols.visa as visa_module
from flex_drivers.srs.sr7270 import SR7270


class FakeRawResource:
    """Emulates the 7270's <text>\\x00<status><overload> USB framing."""

    def __init__(self):
        self.raw_written = []
        self.replies = {"ID": "7270", "VER": "3.09"}
        self._chunks = []
        self.timeout = None
        self.closed = False

    def write_raw(self, data: bytes):
        self.raw_written.append(data)
        cmd = data.decode("ascii").rstrip("\x00")
        framed = self.replies.get(cmd, "") + "\x00\x01\x00"
        # Deliver in two chunks to exercise the chunked read loop.
        mid = max(1, len(framed) // 2)
        self._chunks = [framed[:mid], framed[mid:]]

    def read(self):
        if not self._chunks:
            raise RuntimeError("no more data")
        return self._chunks.pop(0)

    def close(self):
        self.closed = True


class FakeResourceManager:
    def __init__(self, *args):
        self.resource = FakeRawResource()

    def open_resource(self, resource, **kwargs):
        self.resource.timeout = kwargs.get("timeout")
        return self.resource


@pytest.fixture
def lockin(monkeypatch):
    monkeypatch.setattr(visa_module.pyvisa, "ResourceManager", FakeResourceManager)
    return SR7270(serial="10105267")


def test_query_framing_and_status_bytes(lockin):
    text, status, overload = lockin.query("ID")
    assert (text, status, overload) == ("7270", 1, 0)
    assert lockin._resource.raw_written == [b"ID\x00"]
    assert lockin._resource.chunk_size == 102400
    assert lockin._resource.read_termination is None


def test_single_point_reads(lockin):
    lockin._resource.replies.update({"X.": "1.5e-06", "Y.": "-2.5e-07"})
    assert lockin.get_xy() == (1.5e-06, -2.5e-07)
    assert lockin._resource.raw_written == [b"X.\x00", b"Y.\x00"]
    assert lockin.parameters["x"].get() == 1.5e-06


def test_oscillator_set_and_get(lockin):
    lockin._resource.replies["FRQ."] = "100000.0"
    lockin.set_ref_frequency(1000.0)
    assert lockin.get_ref_frequency() == 100000.0
    assert lockin._resource.raw_written == [b"FRQ 1000.0\x00", b"FRQ.\x00"]


def test_curve_buffer_readout(lockin):
    lockin._resource.replies["DC. 0"] = "1.0\n2.0\n\n3.5"
    assert lockin.read_curve_buffer(0) == [1.0, 2.0, 3.5]
    assert lockin._resource.raw_written == [b"DC. 0\x00"]


def test_acquisition_status_parsing(lockin):
    lockin._resource.replies["M"] = "2, 0, 1, 512"
    assert lockin.get_acquisition_status() == (2, 0, 1, 512)
    assert lockin.get_num_stored_points() == 512


def test_idn(lockin):
    assert lockin.idn() == {
        "vendor": "Signal Recovery",
        "model": "7270",
        "serial": "10105267",
        "firmware": "3.09",
    }
