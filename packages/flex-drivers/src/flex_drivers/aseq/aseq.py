"""ASEQ Instruments CCD spectrometer, via the vendor's ``libspectr`` DLL.

Ported from <https://github.com/PVSensors/ASQESpectrometer> (MIT). Unlike
every other driver here, this isn't a wire protocol (VISA/TCP/serial/ZMQ) --
it's a local C library reached through ``ctypes``, so it subclasses
:class:`~flex.instrument.Instrument` directly instead of a protocol base.
"""

from __future__ import annotations

import ctypes
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from flex.instrument import Enum, Instrument, Numbers

_LIB_DIR = Path(__file__).parent / "lib"

_DEFAULT_PARAMS = {
    "num_of_scans": 1,
    "num_of_blank_scans": 0,
    "exposure_time": 1000,  # device units of 10 us (so 1000 = 10 ms)
    "scan_mode": 3,
    "num_of_start_element": 0,
    "num_of_end_element": 3647,
    "reduction_mode": 0,
}

_NUM_PIXELS = 3653  # calibration table length (a few guard pixels beyond the 3648-element CCD)


def _lib_filename(plat: str = sys.platform, arch: str = "") -> str:
    """The ``libspectr`` file for this platform (see :data:`_LIB_DIR`)."""
    if plat == "win32":
        arch = arch or platform.architecture()[0]
        return "libspectr64bit.dll" if arch == "64bit" else "libspectr.dll"
    if plat == "darwin":
        return "libspectr.dylib"
    return "libspectr.so"


class ASEQSpectrometer(Instrument):
    """ASEQ CCD spectrometer: connects over USB via the vendor DLL, no address needed.

    ``get_raw_spectrum`` / ``get_normalized_spectrum`` / ``get_calibrated_spectrum``
    each return ``(wavelength, intensity)`` (raw has no wavelength axis and no
    calibration needed). ``spectrum`` is a :class:`~flex.instrument.Parameter`
    over the calibrated intensity alone -- the loggable/sweepable quantity,
    e.g. ``[instruments.spectrometer] log = ["spectrum"]``.
    """

    def __init__(
        self,
        name: str = "spectrometer",
        *,
        calibration_file: str | Path | None = None,
        capture_timeout: float = 30.0,
        **kwargs: Any,
    ):
        """
        Args:
            name: Instrument name used in logs, snapshots, and experiments.
            calibration_file: Path to a ``.clbr``/``calib.txt`` file. If not
                given, calibration is read from the device's own flash memory
                on first use (the vendor library's default behavior).
            capture_timeout: Seconds to wait for a frame before raising
                ``TimeoutError`` (the vendor code polls forever; a shared
                instrument server can't afford that).
        """
        super().__init__(name, **kwargs)
        self._capture_timeout = capture_timeout
        self._calibration_file = calibration_file
        self._calibration_loaded = False
        self._wavelength: np.ndarray | None = None
        self._norm_coef: np.ndarray | None = None
        self._power_coef: np.ndarray | None = None
        self._bck_at: float = 1.0

        self._params = dict(_DEFAULT_PARAMS)
        self.lib = ctypes.CDLL(str(_LIB_DIR / _lib_filename()))
        self._setup_prototypes()
        self._connect()

        self.exposure_time = self.add_parameter(
            "exposure_time", getter=lambda: self._params["exposure_time"],
            setter=lambda v: self._set_param("exposure_time", v),
            unit="10us", vals=Numbers(min=1), doc="Integration time, in units of 10 us.",
        )
        self.num_of_scans = self.add_parameter(
            "num_of_scans", getter=lambda: self._params["num_of_scans"],
            setter=lambda v: self._set_param("num_of_scans", v),
            vals=Numbers(1, 137), doc="Spectral averages per measurement.",
        )
        self.num_of_blank_scans = self.add_parameter(
            "num_of_blank_scans", getter=lambda: self._params["num_of_blank_scans"],
            setter=lambda v: self._set_param("num_of_blank_scans", v),
            vals=Numbers(0, 137), doc="Background reference measurements.",
        )
        self.scan_mode = self.add_parameter(
            "scan_mode", getter=lambda: self._params["scan_mode"],
            setter=lambda v: self._set_param("scan_mode", v),
            vals=Enum(0, 1, 2, 3),
            doc="0=continuous+trigger, 1=idle-then-trigger, 2=idle between frames, 3=averaging.",
        )
        self.reduction_mode = self.add_parameter(
            "reduction_mode", getter=lambda: self._params["reduction_mode"],
            setter=lambda v: self._set_param("reduction_mode", v),
            vals=Enum(0, 1, 2, 3), doc="Pixel averaging: 0=none, 1=2:1, 2=4:1, 3=8:1.",
        )
        self.spectrum = self.add_parameter(
            "spectrum", getter=lambda: self.get_calibrated_spectrum()[1],
            unit="a.u.", doc="Calibrated intensity spectrum (see get_*_spectrum for the wavelength axis).",
        )

        self._configure_acquisition()

    # -- ctypes setup ----------------------------------------------------------

    def _setup_prototypes(self) -> None:
        self.lib.connectToDevice.argtypes = [ctypes.c_char_p]
        self.lib.connectToDevice.restype = ctypes.c_int
        self.lib.disconnectDevice.argtypes = []
        self.lib.disconnectDevice.restype = None
        self.lib.setAcquisitionParameters.argtypes = [
            ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint8, ctypes.c_uint32,
        ]
        self.lib.setAcquisitionParameters.restype = ctypes.c_int
        self.lib.setFrameFormat.argtypes = [
            ctypes.c_uint16, ctypes.c_uint16, ctypes.c_uint8, ctypes.POINTER(ctypes.c_uint16),
        ]
        self.lib.setFrameFormat.restype = ctypes.c_int
        self.lib.getStatus.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.POINTER(ctypes.c_uint16)]
        self.lib.getStatus.restype = ctypes.c_int
        self.lib.getFrame.argtypes = [ctypes.POINTER(ctypes.c_uint16), ctypes.c_uint16]
        self.lib.getFrame.restype = ctypes.c_int
        self.lib.triggerAcquisition.argtypes = []
        self.lib.triggerAcquisition.restype = ctypes.c_int
        self.lib.readFlash.argtypes = [ctypes.POINTER(ctypes.c_uint8), ctypes.c_uint32, ctypes.c_uint32]
        self.lib.readFlash.restype = ctypes.c_int

    def _connect(self) -> None:
        result = self.lib.connectToDevice(None)
        if result != 0:
            raise ConnectionError(f"{self.name}: connectToDevice failed (code {result})")

    def close(self) -> None:
        self.lib.disconnectDevice()

    def idn(self) -> dict[str, str | None]:
        return {"vendor": "ASEQ Instruments", "model": type(self).__name__, "serial": None, "firmware": None}

    # -- configuration -----------------------------------------------------

    def _set_param(self, name: str, value: Any) -> None:
        self._params[name] = value
        self._configure_acquisition()

    def _configure_acquisition(self) -> None:
        p = self._params
        self.lib.setAcquisitionParameters(
            ctypes.c_uint16(p["num_of_scans"]), ctypes.c_uint16(p["num_of_blank_scans"]),
            ctypes.c_uint8(p["scan_mode"]), ctypes.c_uint32(p["exposure_time"]),
        )
        num_pixels = ctypes.c_uint16(0)
        self.lib.setFrameFormat(
            ctypes.c_uint16(p["num_of_start_element"]), ctypes.c_uint16(p["num_of_end_element"]),
            ctypes.c_uint8(p["reduction_mode"]), ctypes.pointer(num_pixels),
        )

    # -- acquisition ---------------------------------------------------------

    def capture_frame(self) -> np.ndarray:
        """Trigger and read one raw frame (uint16 counts, un-background-subtracted)."""
        self.lib.triggerAcquisition()
        status = ctypes.c_uint8(0)
        frames = ctypes.c_uint16(0)
        deadline = time.monotonic() + self._capture_timeout
        while frames.value == 0:
            if time.monotonic() > deadline:
                raise TimeoutError(f"{self.name}: no frame within {self._capture_timeout}s")
            time.sleep(0.025)
            self.lib.getStatus(ctypes.pointer(status), ctypes.pointer(frames))
        buffer = (ctypes.c_uint16 * 3694)()
        self.lib.getFrame(buffer, 65535)
        return np.ctypeslib.as_array(buffer).copy()

    def get_raw_spectrum(self) -> np.ndarray:
        """The full raw frame, uint16 counts."""
        return self.capture_frame()

    def _background_subtracted(self) -> np.ndarray:
        data = self.capture_frame()
        background = (np.mean(data[15:31]) + np.mean(data[3686:3692])) / 2
        return data[32:3685].astype(np.float64) - background

    def get_normalized_spectrum(self) -> tuple[np.ndarray, np.ndarray]:
        """``(wavelength, intensity)``, background-subtracted and flat-field normalized."""
        self._ensure_calibration()
        data = self._background_subtracted() / self._norm_coef
        return self._wavelength, data

    def get_calibrated_spectrum(self) -> tuple[np.ndarray, np.ndarray]:
        """``(wavelength, intensity)``, additionally power-calibrated."""
        wavelength, data = self.get_normalized_spectrum()
        data = data * self._power_coef / (self._params["exposure_time"] * self._bck_at)
        return wavelength, data

    # -- calibration ---------------------------------------------------------

    def read_flash(self, offset: int = 0, size: int = 1000) -> bytes:
        buffer = (ctypes.c_uint8 * size)()
        result = self.lib.readFlash(buffer, offset, size)
        if result != 0:
            raise RuntimeError(f"{self.name}: readFlash failed (code {result})")
        return bytes(buffer)

    def _read_calibration_from_flash(self) -> bytes:
        offset, chunk, cap = 0, 1000, 100_000
        data = bytearray()
        while offset <= cap:
            chunk_bytes = self.read_flash(offset, chunk)
            stop = chunk_bytes.find(b"\xff\xff")
            if stop != -1:
                data.extend(chunk_bytes[:stop])
                break
            data.extend(chunk_bytes)
            offset += chunk
        return bytes(data)

    def _ensure_calibration(self) -> None:
        """Load the wavelength axis and normalization/power coefficients.

        Source order: an explicit ``calibration_file=``, else ``calib.txt``
        in the current directory, else the device's own flash memory.
        """
        if self._calibration_loaded:
            return
        path = None
        for candidate in (self._calibration_file, "calib.txt"):
            if candidate and os.path.exists(candidate):
                path = candidate
                break
        if path:
            with open(path, encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
        else:
            raw = self._read_calibration_from_flash().decode("utf-8", errors="ignore")
            lines = [line.strip() for line in raw.splitlines() if line.strip()]

        try:
            self._bck_at = float(lines[1])
            start = next(i for i, ln in enumerate(lines) if _is_wavelength(ln))
            self._wavelength = np.array(lines[start:start + _NUM_PIXELS], dtype=np.float64)
            start_norm = start + _NUM_PIXELS
            self._norm_coef = np.array(lines[start_norm:start_norm + _NUM_PIXELS], dtype=np.float64)
            self._norm_coef[self._norm_coef == 0] = 1.0
            start_power = start_norm + _NUM_PIXELS
            self._power_coef = np.array(lines[start_power:start_power + _NUM_PIXELS], dtype=np.float64)
        except (IndexError, StopIteration, ValueError) as e:
            self.log.warning("Calibration data unavailable (%s); using uncalibrated placeholders", e)
            self._bck_at = 1.0
            self._wavelength = np.linspace(385.0, 1089.0, _NUM_PIXELS)
            self._norm_coef = np.ones(_NUM_PIXELS)
            self._power_coef = np.ones(_NUM_PIXELS)
        self._calibration_loaded = True


def _is_wavelength(line: str) -> bool:
    try:
        return float(line) > 200.0  # nm; used to locate the wavelength table in the calibration blob
    except ValueError:
        return False
