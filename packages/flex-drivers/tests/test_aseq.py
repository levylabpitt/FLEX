"""ASEQSpectrometer tests with a fake libspectr (no real DLL/hardware)."""

import numpy as np
import pytest

import flex_drivers.aseq.aseq as aseq_module
from flex_drivers.aseq import ASEQSpectrometer


def _v(x):
    """Unwrap a ctypes scalar (c_uint16(5) -> 5) for readable call assertions."""
    return x.value if hasattr(x, "value") else x


class FakeLib:
    """Stands in for the real ctypes.CDLL handle.

    Its "functions" are plain closures (not bound methods) assigned as
    instance attributes, because the driver sets ``.argtypes``/``.restype``
    on each one -- exactly like real ctypes function pointers, and unlike
    Python bound methods, which don't support arbitrary attributes.
    """

    def __init__(self):
        self.calls = []
        self.connect_result = 0
        self.frame = np.zeros(3694)
        self.flash = b""

        def connectToDevice(name):
            self.calls.append(("connectToDevice", name))
            return self.connect_result

        def disconnectDevice():
            self.calls.append(("disconnectDevice",))

        def setAcquisitionParameters(num_scans, num_blank, mode, exposure):
            self.calls.append((
                "setAcquisitionParameters", _v(num_scans), _v(num_blank), _v(mode), _v(exposure),
            ))
            return 0

        def setFrameFormat(start, end, reduction, num_pixels_ptr):
            self.calls.append(("setFrameFormat", _v(start), _v(end), _v(reduction)))
            return 0

        def getStatus(status_ptr, frames_ptr):
            frames_ptr.contents.value = 1
            return 0

        def getFrame(buffer, max_size):
            self.calls.append(("getFrame", max_size))
            for i in range(len(buffer)):
                buffer[i] = int(self.frame[i])
            return 0

        def triggerAcquisition():
            self.calls.append(("triggerAcquisition",))
            return 0

        def readFlash(buffer, offset, size):
            chunk = self.flash[offset:offset + size]
            for i in range(size):
                buffer[i] = chunk[i] if i < len(chunk) else 0
            return 0

        self.connectToDevice = connectToDevice
        self.disconnectDevice = disconnectDevice
        self.setAcquisitionParameters = setAcquisitionParameters
        self.setFrameFormat = setFrameFormat
        self.getStatus = getStatus
        self.getFrame = getFrame
        self.triggerAcquisition = triggerAcquisition
        self.readFlash = readFlash


@pytest.fixture
def fake_lib(monkeypatch):
    lib = FakeLib()
    monkeypatch.setattr(aseq_module.ctypes, "CDLL", lambda path: lib)
    return lib


@pytest.fixture
def spec(fake_lib):
    return ASEQSpectrometer("spec", calibration_file="/nonexistent")  # forces the flash fallback


def test_connects_and_configures_on_init(fake_lib):
    ASEQSpectrometer("spec", calibration_file="/nonexistent")
    names = [c[0] for c in fake_lib.calls]
    assert names == ["connectToDevice", "setAcquisitionParameters", "setFrameFormat"]
    assert fake_lib.calls[1] == ("setAcquisitionParameters", 1, 0, 3, 1000)  # defaults


def test_connect_failure_raises(fake_lib):
    fake_lib.connect_result = 7
    with pytest.raises(ConnectionError, match="code 7"):
        ASEQSpectrometer("spec", calibration_file="/nonexistent")


def test_setting_a_parameter_reconfigures_immediately(spec, fake_lib):
    fake_lib.calls.clear()
    spec.exposure_time(2500)
    assert spec.exposure_time() == 2500
    assert fake_lib.calls == [
        ("setAcquisitionParameters", 1, 0, 3, 2500),
        ("setFrameFormat", 0, 3647, 0),
    ]


def test_parameter_validators_reject_bad_values(spec):
    with pytest.raises(ValueError):
        spec.num_of_scans(200)  # max is 137
    with pytest.raises(ValueError):
        spec.scan_mode(9)  # not in 0..3


def test_capture_timeout(fake_lib, monkeypatch):
    def never_ready(status_ptr, frames_ptr):
        frames_ptr.contents.value = 0

    fake_lib.getStatus = never_ready
    monkeypatch.setattr(aseq_module.time, "sleep", lambda s: None)
    spec = ASEQSpectrometer("spec", calibration_file="/nonexistent", capture_timeout=0.01)
    with pytest.raises(TimeoutError):
        spec.get_raw_spectrum()


def test_raw_spectrum_reads_full_frame(spec, fake_lib):
    fake_lib.frame = np.arange(3694, dtype=np.float64)
    data = spec.get_raw_spectrum()
    assert len(data) == 3694
    assert data[0] == 0 and data[-1] == 3693


def test_uncalibrated_fallback_when_no_calibration_available(spec):
    wavelength, intensity = spec.get_calibrated_spectrum()
    assert len(wavelength) == len(intensity) == 3653
    assert wavelength[0] == pytest.approx(385.0)


def test_calibration_file_is_used_when_given(fake_lib, tmp_path):
    lines = ["1.0", "1.5"]  # [name/whatever, bck_aT]
    lines += [str(500.0 + i) for i in range(3653)]  # wavelength (all > 200 -> detected)
    lines += ["2.0"] * 3653  # norm_coef
    lines += ["4.0"] * 3653  # power_coef
    calib = tmp_path / "calib.clbr"
    calib.write_text("\n".join(lines), encoding="utf-8")

    spec = ASEQSpectrometer("spec", calibration_file=str(calib))
    fake_lib.frame = np.full(3694, 100.0)  # flat frame -> background subtraction -> 0 signal
    wavelength, intensity = spec.get_normalized_spectrum()
    assert wavelength[0] == pytest.approx(500.0)
    assert intensity == pytest.approx(np.zeros(3653), abs=1e-9)


def test_spectrum_parameter_matches_get_calibrated_spectrum(spec):
    _, expected = spec.get_calibrated_spectrum()
    assert spec.spectrum() == pytest.approx(expected)


def test_idn(spec):
    idn = spec.idn()
    assert idn["vendor"] == "ASEQ Instruments"
    assert idn["model"] == "ASEQSpectrometer"


def test_close_disconnects(spec, fake_lib):
    spec.close()
    assert ("disconnectDevice",) in fake_lib.calls


@pytest.mark.parametrize(
    ("plat", "arch", "expected"),
    [
        ("win32", "64bit", "libspectr64bit.dll"),
        ("win32", "32bit", "libspectr.dll"),
        ("darwin", "", "libspectr.dylib"),
        ("linux", "", "libspectr.so"),
    ],
)
def test_lib_filename_per_platform(plat, arch, expected):
    assert aseq_module._lib_filename(plat, arch) == expected
