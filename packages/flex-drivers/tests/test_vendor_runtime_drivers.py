"""Drivers that talk through a vendor runtime (.NET, COM, DLL), with fakes in place
of the runtime so they run without the vendor software or hardware."""

import ctypes

import pytest

import flex_drivers.newport.conex_agp as conex_module
import flex_drivers.newport.nf8742 as nf8742_module
import flex_drivers.ophir.nova as nova_module
from flex_drivers.newport import NF8742, ConexAGP
from flex_drivers.ophir import OphirNova
from flex_drivers.sphere import DScan

# -- Newport CONEX-AGP -----------------------------------------------------------


class FakeConex:
    open_status = 0

    def __init__(self):
        self.closed = False
        self.position = 1.25
        self.last = None

    def OpenInstrument(self, port):  # noqa: N802 - the vendor library's name
        return self.open_status

    def CloseInstrument(self):  # noqa: N802
        self.closed = True
        return 0

    def VE(self, addr):  # noqa: N802
        return 0, "CONEX-AGP 1.0"

    def TP(self, addr):  # noqa: N802
        return 0, self.position

    def PA_Set(self, addr, position):  # noqa: N802
        if position > 10:
            return -1, "limit reached"
        self.position, self.last = position, ("PA", position)
        return 0, ""

    def PR_Set(self, addr, delta):  # noqa: N802
        self.position += delta
        return 0, ""

    def ST(self, addr):  # noqa: N802
        return 0

    def OR(self, addr, err):  # noqa: N802
        return 0, ""

    def TS(self, addr, code, state, err):  # noqa: N802
        return 0, "0", "READY", ""


@pytest.fixture
def conex(monkeypatch):
    fake = FakeConex()
    monkeypatch.setattr(conex_module, "_load_commands", lambda dll_dir=None: lambda: fake)
    return fake


def test_conex_moves_and_reads(conex):
    with ConexAGP(port="COM3") as stage:
        assert stage.address == "COM3"
        assert stage.get_version() == "CONEX-AGP 1.0"
        stage.move_absolute(2.0)
        stage.move_relative(0.5)
        assert stage.parameters["position"].get() == 2.5
        stage.stop()
        stage.home()
        assert stage.get_status() == {"error_code": "0", "state": "READY", "error": ""}
    assert conex.closed


def test_conex_reports_a_failed_command(conex):
    with ConexAGP() as stage, pytest.raises(RuntimeError, match="limit reached"):
        stage.move_absolute(11)


def test_conex_open_failure(conex):
    conex.open_status = -1
    with pytest.raises(ConnectionError, match="COM8"):
        ConexAGP()


# -- Newport NF8742 --------------------------------------------------------------


class FakeBuilder:
    def __init__(self, size):
        self.text = ""

    def ToString(self):  # noqa: N802
        return self.text


class FakeUSB:
    devices = 1

    def __init__(self, _flag):
        self.sent, self.closed, self.motion = [], False, iter(["0", "0", "1"])

    def OpenDevices(self, _a, _b):  # noqa: N802
        return True

    def GetDeviceTable(self):  # noqa: N802
        table = type("Table", (), {"Count": self.devices})()
        table.GetEnumerator = lambda: type("Enum", (), {"MoveNext": lambda s: True, "Key": "8742-1"})()
        return table

    def Query(self, key, command, reply):  # noqa: N802
        self.sent.append(command)
        reply.text = {"*IDN?": "New_Focus 8742", "1TP?": "1200", "1VA?": "2000"}.get(command, "")
        if command.endswith("MD?"):
            reply.text = next(self.motion)
        return True

    def CloseDevices(self):  # noqa: N802
        self.closed = True


@pytest.fixture
def usb(monkeypatch):
    made = []

    def factory(flag):
        made.append(FakeUSB(flag))
        return made[-1]

    monkeypatch.setattr(nf8742_module, "_load_usb", lambda dll_dir=None: (factory, FakeBuilder))
    return made


def test_nf8742_commands(usb):
    with NF8742(axis=2) as motor:
        assert motor.idn()["model"] == "New_Focus 8742"
        motor.move_absolute(500)
        motor.move_relative(-20)
        motor.move_direction(False)
        motor.set_velocity(1500)
        motor.stop()
        assert usb[0].sent == ["*IDN?", "2PA500", "2PR-20", "2MV-", "2VA1500", "2ST"]
    assert usb[0].closed


def test_nf8742_reads_numbers_and_waits_for_a_move(usb):
    with NF8742(axis=1) as motor:
        assert motor.parameters["position"].get() == 1200
        assert motor.parameters["velocity"].get() == 2000
        assert motor.move_and_wait_relative(10, timeout=5) == 1200
        assert usb[0].sent.count("1MD?") == 3  # polled until the controller said done


def test_nf8742_rejects_a_bad_axis_and_a_missing_controller(usb, monkeypatch):
    with pytest.raises(ValueError, match="Axis"):
        NF8742(axis=5)
    monkeypatch.setattr(FakeUSB, "devices", 0)
    with pytest.raises(RuntimeError, match="No 8742"):
        NF8742()
    assert usb[-1].closed


# -- Ophir Nova ------------------------------------------------------------------


class FakeOphir:
    serials = ["SN-1"]

    def __init__(self):
        self.calls = []

    def StopAllStreams(self):  # noqa: N802
        self.calls.append("stop")

    def CloseAll(self):  # noqa: N802
        self.calls.append("close")

    def ScanUSB(self):  # noqa: N802
        return self.serials

    def OpenUSBDevice(self, serial):  # noqa: N802
        return 7

    def IsSensorExists(self, handle, channel):  # noqa: N802
        return True

    def StartStream(self, handle, channel):  # noqa: N802
        self.calls.append("start")

    def GetData(self, handle, channel):  # noqa: N802
        return [[0.001, 0.002]]


@pytest.fixture
def ophir(monkeypatch):
    fake = FakeOphir()
    monkeypatch.setattr(nova_module, "_dispatch", lambda: fake)
    return fake


def test_ophir_reads_power(ophir):
    with OphirNova() as meter:
        assert meter.serial == "SN-1"
        assert meter.read_power(settle=0) == 0.002
        assert meter.parameters["power"].unit == "W"
    assert ophir.calls[-1] == "close"


def test_ophir_wrong_or_missing_meter(ophir, monkeypatch):
    with pytest.raises(RuntimeError, match="SN-9"):
        OphirNova(serial_number="SN-9")
    monkeypatch.setattr(FakeOphir, "serials", [])
    with pytest.raises(RuntimeError, match="No Ophir meter"):
        OphirNova()


# -- Sphere d-scan ---------------------------------------------------------------


class FakeDScanLib:
    """The DLL's C functions; a nonzero return is an error with a message."""

    def __init__(self):
        self.insertion, self.fail_next, self.destroyed = 12.3456, False, False

    def dscan_INVALID_HANDLE(self):  # noqa: N802
        return 0xFFFFFFFF

    def dscan_ERROR_MESSAGE_BUFFER_LEN(self):  # noqa: N802
        return 64

    def dscan_GetLastStatusMessage(self, buffer, size):  # noqa: N802
        buffer.value = b"wedge jammed  "

    def dscan_Create(self, serial, handle_ref):  # noqa: N802
        handle_ref._obj.value = 7
        return 0

    def dscan_Connect(self, handle):  # noqa: N802
        return 0

    def dscan_Disconnect(self, handle):  # noqa: N802
        return 0

    def dscan_Destroy(self, handle):  # noqa: N802
        self.destroyed = True
        return 0

    def dscan_IsConnected(self, handle):  # noqa: N802
        return 1

    def dscanComp_GetFullInsertionRange(self, handle, start, stop):  # noqa: N802
        start._obj.value, stop._obj.value = 0.0, 20.0
        return 0

    def dscanComp_GetInsertion(self, handle, out):  # noqa: N802
        out._obj.value = self.insertion
        return 0

    def dscanComp_SetInsertion(self, handle, value):  # noqa: N802
        if self.fail_next:
            return 1
        self.insertion = value.value
        return 0


@pytest.fixture
def dscan_lib(monkeypatch):
    lib = FakeDScanLib()
    monkeypatch.setattr(ctypes.cdll, "LoadLibrary", lambda path: lib)
    return lib


def test_dscan_insertion(dscan_lib):
    with DScan(library="dscan-library.dll") as scan:
        assert scan.is_connected()
        assert scan.get_full_insertion_range() == (0.0, 20.0)
        assert scan.parameters["insertion"].get() == 12.346
        scan.parameters["insertion"].set(5.0)
        assert dscan_lib.insertion == 5.0
    assert dscan_lib.destroyed


def test_dscan_error_carries_the_library_message(dscan_lib):
    with DScan(library="dscan-library.dll") as scan:
        dscan_lib.fail_next = True
        with pytest.raises(RuntimeError, match="wedge jammed"):
            scan.set_insertion(1.0)
