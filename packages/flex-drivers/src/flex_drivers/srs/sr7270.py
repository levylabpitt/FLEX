"""SR7270 DSP lock-in amplifier (Signal Recovery / Ametek) over raw USB VISA."""

from __future__ import annotations

import time

import numpy as np

from flex_protocols import VISAInstrument


class SR7270(VISAInstrument):
    """Driver for the 7270 DSP lock-in amplifier via its RAW USB VISA resource.

    The instrument frames every USB response as ``<text>\\x00<status><overload>``:
    the payload is NULL-terminated and followed by a status byte and an overload
    byte. Every command — including sets — produces such a reply, so all traffic
    goes through :meth:`query`, which returns the ``(text, status, overload)``
    tuple.
    """

    _USB_RESOURCE = "USB0::0x0A2D::0x001B::{serial}::RAW"

    def __init__(
        self,
        name: str = "sr7270",
        serial: str = "",
        *,
        timeout: float = 10.0,
        backend: str = "",
        **kwargs,
    ):
        """
        Args:
            name: Instrument name used in logs, snapshots, and experiments.
            serial: SR7270 USB serial number (string), e.g. ``"10105267"``.
            timeout: Seconds to wait for responses (default 10 s for large
                curve-buffer transfers).
            backend: Optional VISA library spec (e.g. ``"@py"``).
        """
        resource = self._USB_RESOURCE.format(serial=serial)
        super().__init__(name, resource, timeout=timeout, backend=backend, **kwargs)
        self._serial_number = serial
        # The RAW USB endpoint has no termination character; responses are
        # framed by the NULL + status bytes instead. Large chunks speed up
        # curve-buffer transfers.
        self._resource.read_termination = None
        self._resource.chunk_size = 102400

        self.add_parameter("x", getter=self.get_x, unit="V", doc="X channel output.")
        self.add_parameter("y", getter=self.get_y, unit="V", doc="Y channel output.")
        self.add_parameter("magnitude", getter=self.get_magnitude, unit="V", doc="Magnitude R.")
        self.add_parameter(
            "ref_frequency",
            getter=self.get_ref_frequency,
            setter=self.set_ref_frequency,
            unit="Hz",
            doc="Internal oscillator frequency.",
        )
        self.add_parameter(
            "ref_amplitude",
            getter=self.get_ref_amplitude,
            setter=self.set_ref_amplitude,
            unit="V",
            doc="Oscillator amplitude.",
        )

    # ------------------------------------------------------------
    # Framing
    # ------------------------------------------------------------

    def query(self, cmd: str) -> tuple[str, int, int]:
        """Send a command and read the framed response.

        Returns:
            tuple: ``(response_str, status_byte, overload_byte)``
        """
        self.log.debug("query: %s", cmd)
        # USB commands must be terminated with NULL.
        self._resource.write_raw((cmd + "\x00").encode("ascii"))
        return self.read()

    def read(self) -> tuple[str, int, int]:
        """Read chunks until the NULL + status + overload frame is complete.

        Returns:
            tuple: ``(response_str, status_byte, overload_byte)``
        """
        response = ""
        for _ in range(100):  # max 100 chunks to prevent an infinite loop
            try:
                response += self._resource.read()
                # Complete termination is \x00<status><overload>.
                if len(response) >= 3 and "\x00" in response:
                    null_pos = response.find("\x00")
                    if len(response) >= null_pos + 3:
                        break
            except Exception:
                break

        if "\x00" in response:
            null_pos = response.find("\x00")
            status = ord(response[null_pos + 1]) & 0x8F if len(response) >= null_pos + 2 else 0
            overload = ord(response[null_pos + 2]) if len(response) >= null_pos + 3 else 0
            text = response[:null_pos].rstrip()
        else:
            status = overload = 0
            text = response.rstrip()
        self.log.debug("reply: %r status=0x%02x overload=0x%02x", text, status, overload)
        return text, status, overload

    # ------------------------------------------------------------
    # Basic queries
    # ------------------------------------------------------------

    def get_id(self) -> str:
        """Get instrument identification string."""
        return self.query("ID")[0]

    def get_ver(self) -> str:
        """Get instrument firmware version."""
        return self.query("VER")[0]

    def idn(self) -> dict[str, str | None]:
        return {
            "vendor": "Signal Recovery",
            "model": self.get_id(),
            "serial": self._serial_number or None,
            "firmware": self.get_ver(),
        }

    # ------------------------------------------------------------
    # Reference / Oscillator
    # ------------------------------------------------------------

    def set_ref_frequency(self, freq_hz: float) -> None:
        """Set internal oscillator frequency in Hz."""
        self.query(f"FRQ {freq_hz}")

    def get_ref_frequency(self) -> float:
        """Get internal oscillator frequency in Hz."""
        return float(self.query("FRQ.")[0])

    def set_ref_amplitude(self, amp_volts: float) -> None:
        """Set oscillator amplitude in Volts."""
        self.query(f"OA {amp_volts}")

    def get_ref_amplitude(self) -> float:
        """Get oscillator amplitude in Volts."""
        return float(self.query("OA.")[0])

    def set_ref_phase(self, phase_deg: float) -> None:
        """Set reference phase shift in degrees."""
        self.query(f"REFP. {phase_deg}")

    def get_ref_phase(self) -> float:
        """Get reference phase shift in degrees."""
        return float(self.query("REFP.")[0])

    # ------------------------------------------------------------
    # Signal Channel Setup
    # ------------------------------------------------------------

    def set_sensitivity(self, index: int) -> None:
        """Set full-scale sensitivity range (1-27, see manual)."""
        self.query(f"SEN {index}")

    def get_sensitivity(self) -> int:
        """Get current sensitivity range index."""
        return int(self.query("SEN")[0])

    def set_time_constant(self, index: int) -> None:
        """Set output time constant (0-29, see manual)."""
        self.query(f"TC {index}")

    def get_time_constant(self) -> int:
        """Get current time constant index."""
        return int(self.query("TC")[0])

    def auto_measure(self) -> None:
        """Perform Auto-Measure (ASM) operation."""
        self.query("ASM")

    # ------------------------------------------------------------
    # Single-point Data Acquisition
    # ------------------------------------------------------------

    def get_x(self) -> float:
        """Get X channel output in Volts."""
        return float(self.query("X.")[0])

    def get_y(self) -> float:
        """Get Y channel output in Volts."""
        return float(self.query("Y.")[0])

    def get_magnitude(self) -> float:
        """Get magnitude output in Volts."""
        return float(self.query("MAG.")[0])

    def get_phase(self) -> float:
        """Get phase output in degrees."""
        return float(self.query("PHA.")[0])

    def get_xy(self) -> tuple[float, float]:
        """Get (X, Y) tuple in Volts."""
        return self.get_x(), self.get_y()

    def get_rtheta(self) -> tuple[float, float]:
        """Get (Magnitude, Phase) tuple."""
        return self.get_magnitude(), self.get_phase()

    # ------------------------------------------------------------
    # Continuous Data Acquisition (Curve Buffer)
    # ------------------------------------------------------------

    def setup_curve_buffer(self, buffer_size: int) -> None:
        """Set curve buffer length.

        Args:
            buffer_size: Number of points to store (max 100000).
        """
        self.query(f"LEN {buffer_size}")

    def configure_curve_quantity(self, cbd_value: int) -> None:
        """Configure what quantities to store in the curve buffer.

        NOTE: For floating point readout (``DC.`` command), bit 4
        (Sensitivity=16) MUST be included when storing X, Y, Magnitude,
        or Noise.

        Args:
            cbd_value: Bit mask - combine with bitwise OR:
                1=X, 2=Y, 4=Mag, 8=Phase, 16=Sensitivity,
                32=ADC1, 64=ADC2, 128=ADC3

        Examples:
            17 (1+16): X + Sensitivity (floating point)
            19 (1+2+16): X + Y + Sensitivity (floating point)
        """
        self.query(f"CBD {cbd_value}")

    def set_storage_interval(self, interval_us: float) -> None:
        """Set time interval between data points.

        Args:
            interval_us: Interval in microseconds (min 1000 us = 1 ms).
        """
        self.query(f"STR {interval_us}")

    def start_continuous_acquisition(self, mode: int = 0) -> None:
        """Start continuous data acquisition.

        Args:
            mode: 0=start immediately, 1=start on trigger, 2=triggered start/stop.
        """
        self.query(f"TDC {mode}")

    def halt_acquisition(self) -> None:
        """Stop curve acquisition."""
        self.query("HC")

    def get_acquisition_status(self) -> tuple[int, ...]:
        """Get curve acquisition status.

        Returns:
            tuple: ``(status, num_sweeps, status_byte, num_points)``
                status: 0=idle, 2=running, 6=halted
                num_points: Number of points acquired
        """
        resp = self.query("M")[0]
        return tuple(int(x.strip()) for x in resp.split(","))

    def get_num_stored_points(self) -> int:
        """Get number of points stored in buffer."""
        return self.get_acquisition_status()[3]

    def read_curve_buffer(self, bit_number: int) -> list[float]:
        """Read data from the curve buffer.

        Args:
            bit_number: Bit position from CBD (0=X, 1=Y, 2=Mag, 3=Phase, etc.)

        Returns:
            list of float values
        """
        resp = self.query(f"DC. {bit_number}")[0]
        if not resp:
            return []

        values = []
        for line in resp.split("\n"):
            line = line.strip()
            if line:
                try:
                    values.append(float(line))
                except ValueError:
                    pass
        return values

    def clear_curve_buffer(self) -> None:
        """Clear the curve buffer."""
        self.query("NC")

    def acquire_continuous(
        self, duration_s: float, sample_rate_hz: float, channel: str = "X"
    ) -> tuple[np.ndarray, np.ndarray]:
        """Perform continuous data acquisition and return time-series data.

        Args:
            duration_s: Acquisition duration in seconds.
            sample_rate_hz: Sample rate in Hz (max 1000 Hz).
            channel: Channel to acquire ('X', 'Y', 'Mag', or 'Phase').

        Returns:
            tuple: ``(timestamps, values)`` as numpy arrays.
                timestamps: Time array in seconds.
                values: Measured values in Volts (or degrees for Phase).

        Example:
            times, x_vals = sr.acquire_continuous(duration_s=10.0, sample_rate_hz=100)
        """
        num_points = int(duration_s * sample_rate_hz)
        interval_us = int(1e6 / sample_rate_hz)  # convert Hz to microseconds

        # Map channel to CBD bit mask and bit number.
        channel_map = {
            "X": (17, 0),  # X + Sensitivity, read bit 0
            "Y": (18, 1),  # Y + Sensitivity, read bit 1
            "Mag": (20, 2),  # Mag + Sensitivity, read bit 2
            "Phase": (8, 3),  # Phase only (no sensitivity needed), read bit 3
        }
        if channel not in channel_map:
            raise ValueError(f"Channel must be one of {list(channel_map.keys())}")
        cbd_value, bit_number = channel_map[channel]

        self.clear_curve_buffer()
        self.setup_curve_buffer(min(num_points, 100000))  # max 100k points
        self.configure_curve_quantity(cbd_value)
        self.set_storage_interval(interval_us)

        self.start_continuous_acquisition(0)
        time.sleep(duration_s)
        self.halt_acquisition()

        values = np.array(self.read_curve_buffer(bit_number))
        timestamps = np.arange(len(values)) / sample_rate_hz
        return timestamps, values
