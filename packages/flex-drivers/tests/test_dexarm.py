"""DexArm tests with a fake serial.Serial (no COM port)."""

import pytest

import flex_protocols.serial as serial_module
from flex_drivers.rotrics import DexArm


class FakeSerial:
    def __init__(self, port, *, baudrate, timeout):
        self.port, self.baudrate, self.timeout = port, baudrate, timeout
        self.written = []
        self.lines = []  # queued readline() replies; "ok" once drained
        self.resets = 0
        self.closed = False

    def write(self, data):
        self.written.append(data)

    def readline(self):
        return self.lines.pop(0) if self.lines else b"ok\r\n"

    def reset_input_buffer(self):
        self.resets += 1

    def close(self):
        self.closed = True


@pytest.fixture
def arm(monkeypatch):
    monkeypatch.setattr(serial_module.pyserial, "Serial", FakeSerial)
    return DexArm(port="COM5")


def test_opens_at_115200_baud_blocking(arm):
    assert arm._serial.baudrate == 115200
    assert arm._serial.timeout is None


def test_go_home_waits_for_ok(arm):
    arm.go_home()
    assert arm._serial.written == [b"M1112\r"]


def test_move_to_builds_gcode(arm):
    arm.move_to(0, 220, 135)
    arm.fast_move_to(z=80.4, feedrate=1000)
    assert arm._serial.written == [b"G1F2000X0Y220Z135\r\n", b"G0F1000Z80\r\n"]


def test_move_no_wait_flushes_input(arm):
    arm.move_to(x=10, wait=False)
    assert arm._serial.written == [b"G1F2000X10\r\n"]
    assert arm._serial.resets == 1


def test_get_current_position_parses_m114(arm):
    arm._serial.lines = [
        b"X:0.00 Y:220.00 Z:135.00 E:0.00 Count X:0 Y:0 Z:0\r\n",
        b"DEXARM Theta A:12.50 B:30.00 C:-7.25\r\n",
        b"ok\r\n",
    ]
    assert arm.get_current_position() == (0.0, 220.0, 135.0, 0.0, 12.5, 30.0, -7.25)
    assert arm._serial.written == [b"M114\r"]
    assert arm._serial.resets == 1


def test_get_module_type(arm):
    arm._serial.lines = [b"LASER\r\n", b"ok\r\n"]
    assert arm.get_module_type() == "LASER"
    assert arm._serial.written == [b"M888\r"]


def test_laser_commands(arm):
    arm.laser_on(128)
    arm.laser_off()
    assert arm._serial.written == [b"M3 S128\r", b"M5\r"]
