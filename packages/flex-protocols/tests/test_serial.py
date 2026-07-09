"""SerialInstrument tests with a fake serial.Serial (no COM port)."""

import pytest

import flex_protocols.serial as serial_module
from flex_protocols import SerialInstrument


class FakeSerial:
    def __init__(self, port, *, baudrate, timeout):
        self.port, self.baudrate, self.timeout = port, baudrate, timeout
        self.written = []
        self.next_reply = b"OK\r\n"
        self.closed = False

    def write(self, data):
        self.written.append(data)

    def read_until(self, terminator):
        return self.next_reply

    def close(self):
        self.closed = True


@pytest.fixture
def fake_serial(monkeypatch):
    monkeypatch.setattr(serial_module.pyserial, "Serial", FakeSerial)


def test_write_and_query(fake_serial):
    inst = SerialInstrument("pump", "COM3", baudrate=115200)
    assert inst.query("STATUS?") == "OK"
    assert inst._serial.written == [b"STATUS?\r\n"]
    assert inst._serial.baudrate == 115200


def test_timeout_raises(fake_serial):
    inst = SerialInstrument("pump", "COM3")
    inst._serial.next_reply = b""  # read_until returns without terminator on timeout
    with pytest.raises(TimeoutError):
        inst.query("STATUS?")


def test_close(fake_serial):
    inst = SerialInstrument("pump", "COM3")
    serial = inst._serial
    inst.close()
    inst.close()
    assert serial.closed
