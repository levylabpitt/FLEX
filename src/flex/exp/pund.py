"""
flex.exp.pund
=============
Reusable PUND (Positive-Up Negative-Down) ferroelectric measurement module
for the NI PXIe-4461 DAQ card in NI 1042 PXI Chassis.

PUND protocol applies a sequence of voltage pulses to a ferroelectric capacitor
and measures the switched (polarization reversal) vs. non-switched charge,
isolating remanent polarization from leakage contributions.

Usage
-----
Basic usage::

    from flex.exp.pund import PUNDMeasurement, PUNDConfig

    cfg = PUNDConfig(
        sample_id="SA40XXX",
        daq_name="Dev2",
        ai_channel="ai0",
        ao_channel="ao0",
        amplitude=5.0,
        sample_rate=204800,
        signal_freq=1000,
        duration=0.005,
        waveform="triangle",    # "triangle", "sine", or "square"
        save_to_file=True,
        save_path=r"C:\\Users\\voodoo\\Desktop\\Aswini_PUND_Data",
    )
    results = PUNDMeasurement(cfg).run()

Or use the convenience runner::

    from flex.exp.pund import PUNDConfig, run_pund
    results = run_pund(PUNDConfig(amplitude=5.0))

Results
-------
``pund.run()`` returns a dict with keys:

- ``"time_ms"``   : 1D ndarray, time axis in milliseconds
- ``"ao"``        : 1D ndarray, the applied output waveform (V)
- ``"ai"``        : 1D ndarray, the measured input waveform (V)
- ``"save_path"`` : str or None, path of the saved TDMS file (if saved)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Optional dependencies — graceful ImportError messages
# ---------------------------------------------------------------------------
try:
    import nidaqmx
    from nidaqmx.constants import AcquisitionType
    _NIDAQMX_AVAILABLE = True
except ImportError:
    _NIDAQMX_AVAILABLE = False

try:
    import matplotlib.pyplot as plt
    _MPL_AVAILABLE = True
except ImportError:
    _MPL_AVAILABLE = False

try:
    from flex.tdms import flexTDMS
    _TDMS_AVAILABLE = True
except ImportError:
    _TDMS_AVAILABLE = False


# ---------------------------------------------------------------------------
# DAQ timing constants for NI PXIe-4461 @ 204800 Hz
# ---------------------------------------------------------------------------
_DAC_DELAY_SAMPLES = 63   # DAC pipeline delay at 204800 Hz
_ADC_DELAY_SAMPLES = 36   # ADC pipeline delay at 204800 Hz
_DEFAULT_DELAY_SAMPLES = _DAC_DELAY_SAMPLES + _ADC_DELAY_SAMPLES  # = 99

WaveformType = Literal["triangle", "sine", "square"]


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------
@dataclass
class PUNDConfig:
    """
    All parameters for a PUND measurement.

    Parameters
    ----------
    sample_id : str
        Label for the DUT (used in the saved filename).
    daq_name : str
        NI-DAQmx device name for the DAQ card (e.g. ``"Dev2"``).
    ai_channel : str
        Analog input channel suffix (e.g. ``"ai0"``).
    ao_channel : str
        Analog output channel suffix (e.g. ``"ao0"``).
    amplitude : float
        Peak amplitude of the applied waveform in Volts.
    sample_rate : int
        DAQ sample rate in Hz. Default 204800 Hz (max rate for PXIe-4461).
    signal_freq : float
        Waveform frequency in Hz.
    duration : float
        Measurement duration in seconds.
    waveform : {"triangle", "sine", "square"}
        Shape of the applied voltage waveform.
    delay_samples : int
        Total pipeline delay (DAC + ADC). Default 99 for PXIe-4461 @ 204800 Hz.
    ao_min_val : float
        AO channel minimum voltage limit.
    ao_max_val : float
        AO channel maximum voltage limit.
    ai_min_val : float
        AI channel minimum voltage limit.
    ai_max_val : float
        AI channel maximum voltage limit.
    ref_clk_src : str
        PXI reference clock source (default ``"PXI_Clk10"``).
    ref_clk_rate : float
        PXI reference clock rate in Hz (default 10 MHz).
    save_to_file : bool
        Whether to save acquired data to a TDMS file.
    save_path : str or Path
        Directory (or full file path) to save the TDMS file.
    plot : bool
        Whether to display a plot after acquisition.
    """
    # Device / channel
    sample_id: str = "SAMPLE"
    daq_name: str = "Dev2"
    ai_channel: str = "ai0"
    ao_channel: str = "ao0"

    # Waveform params
    amplitude: float = 5.0
    sample_rate: int = 204800
    signal_freq: float = 1000.0
    duration: float = 0.005
    waveform: WaveformType = "triangle"

    # DAQ timing
    delay_samples: int = _DEFAULT_DELAY_SAMPLES
    ao_min_val: float = -10.0
    ao_max_val: float = 10.0
    ai_min_val: float = -10.0
    ai_max_val: float = 10.0
    ref_clk_src: str = "PXI_Clk10"
    ref_clk_rate: float = 10e6

    # I/O
    save_to_file: bool = False
    save_path: str = r"."
    plot: bool = True


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------
class PUNDMeasurement:
    """
    Encapsulates a single PUND (Positive-Up Negative-Down) measurement
    using a NI PXIe-4461 DAQ card with synchronised AO/AI acquisition.

    The output waveform is applied on the AO channel; the voltage response
    (and therefore the displacement current, with a series resistor) is
    captured on the AI channel.  The DAC/ADC pipeline delay is automatically
    compensated by padding the AO waveform with trailing zeros and trimming
    the head of the AI data.

    Parameters
    ----------
    **kwargs
        Any field from :class:`PUNDConfig`.  Pass keyword arguments directly;
        they will be forwarded to the config dataclass.

    Examples
    --------
    >>> pund = PUNDMeasurement(amplitude=3.0, duration=0.01, waveform="sine")
    >>> results = pund.run()
    >>> print(results["ai"].shape)
    """

    def __init__(self, config: PUNDConfig):
        self.config = config
        self._ao_waveform: Optional[np.ndarray] = None
        self._ai_waveform: Optional[np.ndarray] = None
        self._time_ms: Optional[np.ndarray] = None
        self._last_save_path: Optional[str] = None

    # ------------------------------------------------------------------
    # Waveform generation
    # ------------------------------------------------------------------
    def _build_waveform(self) -> np.ndarray:
        """Generate the requested AO waveform."""
        cfg = self.config
        num_samples = int(cfg.sample_rate * cfg.duration)
        t = np.arange(num_samples) / cfg.sample_rate
        A = cfg.amplitude
        f = cfg.signal_freq

        if cfg.waveform == "triangle":
            # Phase-shifted so the waveform starts from 0 and ramps positive
            wave = A - 2 * A * np.abs(2 * ((f * t + 0.25) % 1) - 1)
        elif cfg.waveform == "sine":
            wave = A * np.sin(2 * np.pi * f * t)
        elif cfg.waveform == "square":
            wave = A * np.sign(np.sin(2 * np.pi * f * t))
        else:
            raise ValueError(
                f"Unknown waveform type '{cfg.waveform}'. "
                "Choose from 'triangle', 'sine', or 'square'."
            )
        return wave

    # ------------------------------------------------------------------
    # Acquisition
    # ------------------------------------------------------------------
    def acquire(self) -> dict:
        """
        Run the DAQ acquisition.

        Returns
        -------
        dict
            ``{"time_ms": ndarray, "ao": ndarray, "ai": ndarray}``
        """
        if not _NIDAQMX_AVAILABLE:
            raise ImportError(
                "nidaqmx is not installed. "
                "Install it with: pip install nidaqmx"
            )

        cfg = self.config
        ao_waveform = self._build_waveform()
        num_samples = len(ao_waveform)
        total_samples = num_samples + cfg.delay_samples

        ao_padded = np.concatenate([ao_waveform, np.zeros(cfg.delay_samples)])
        ai_ch = f"{cfg.daq_name}/{cfg.ai_channel}"
        ao_ch = f"{cfg.daq_name}/{cfg.ao_channel}"

        with nidaqmx.Task() as ao_task, nidaqmx.Task() as ai_task:
            # --- Configure AO ---
            ao_task.ao_channels.add_ao_voltage_chan(
                ao_ch,
                min_val=cfg.ao_min_val,
                max_val=cfg.ao_max_val,
            )
            ao_task.timing.ref_clk_src = cfg.ref_clk_src
            ao_task.timing.ref_clk_rate = cfg.ref_clk_rate
            ao_task.timing.cfg_samp_clk_timing(
                rate=cfg.sample_rate,
                sample_mode=AcquisitionType.FINITE,
                samps_per_chan=total_samples,
            )

            # --- Configure AI ---
            ai_task.ai_channels.add_ai_voltage_chan(
                ai_ch,
                min_val=cfg.ai_min_val,
                max_val=cfg.ai_max_val,
            )
            ai_task.timing.ref_clk_src = cfg.ref_clk_src
            ai_task.timing.ref_clk_rate = cfg.ref_clk_rate
            ai_task.timing.cfg_samp_clk_timing(
                rate=cfg.sample_rate,
                sample_mode=AcquisitionType.FINITE,
                samps_per_chan=total_samples,
            )

            # AI triggers off AO start — ensures phase-locked synchronisation
            ai_task.triggers.start_trigger.cfg_dig_edge_start_trig(
                f"/{cfg.daq_name}/ao/StartTrigger"
            )

            ao_task.write(ao_padded, auto_start=False)
            ai_task.start()
            ao_task.start()

            raw = ai_task.read(
                number_of_samples_per_channel=total_samples,
                timeout=max(10.0, cfg.duration * 5),
            )
            ao_task.wait_until_done(timeout=max(10.0, cfg.duration * 5))

        raw = np.array(raw)
        ai_waveform = raw[cfg.delay_samples:]           # trim pipeline delay
        t_ms = np.arange(num_samples) / cfg.sample_rate * 1000.0

        self._ao_waveform = ao_waveform
        self._ai_waveform = ai_waveform
        self._time_ms = t_ms

        return {"time_ms": t_ms, "ao": ao_waveform, "ai": ai_waveform}

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------
    def save(self, data: dict, filepath: Optional[str] = None) -> str:
        """
        Save acquired data to a TDMS file.

        Parameters
        ----------
        data : dict
            Output of :meth:`acquire`.
        filepath : str, optional
            Full file path.  If not given, a timestamped path is generated
            from ``config.save_path`` and ``config.device_id``.

        Returns
        -------
        str
            The path of the saved file.
        """
        if not _TDMS_AVAILABLE:
            raise ImportError(
                "flex.tdms is not available. "
                "Make sure flex is installed with TDMS support."
            )

        if filepath is None:
            cfg = self.config
            ts = time.strftime("%Y%m%d_%H%M%S")
            save_dir = Path(cfg.save_path)
            save_dir.mkdir(parents=True, exist_ok=True)
            filepath = str(
                save_dir / f"{cfg.sample_id}_PUND_{ts}.tdms"
            )

        data_dict = {
            "Time": data["time_ms"],
            "AO": data["ao"],
            "AI": data["ai"],
        }
        flexTDMS.write_tdms(filepath, data_dict)
        self._last_save_path = filepath
        print(f"[PUNDMeasurement] Data saved to: {filepath}")
        return filepath

    # ------------------------------------------------------------------
    # Plot
    # ------------------------------------------------------------------
    def plot(self, data: dict) -> None:
        """
        Display AO and AI waveforms.

        Parameters
        ----------
        data : dict
            Output of :meth:`acquire`.
        """
        if not _MPL_AVAILABLE:
            raise ImportError(
                "matplotlib is not installed. "
                "Install it with: pip install matplotlib"
            )

        plt.figure(figsize=(15, 5))
        plt.plot(
            data["time_ms"], data["ao"],
            color="tab:gray", linestyle="-", label="Output Wave (AO)"
        )
        plt.plot(
            data["time_ms"], data["ai"],
            color="tab:red", label="Measured AI Data"
        )
        plt.xlabel("Time (ms)")
        plt.ylabel("Voltage (V)")
        plt.title(
            f"PUND Measurement — {self.config.sample_id} "
            f"| {self.config.waveform.capitalize()} @ {self.config.signal_freq:.0f} Hz "
            f"| A = {self.config.amplitude} V"
        )
        plt.grid(True, alpha=0.5)
        plt.legend()
        plt.tight_layout()
        plt.show()

    # ------------------------------------------------------------------
    # High-level run
    # ------------------------------------------------------------------
    def run(self) -> dict:
        """
        Convenience method: acquire → (optionally) save → (optionally) plot.

        Returns
        -------
        dict
            ``{"time_ms", "ao", "ai", "save_path"}``
        """
        print(
            f"[PUNDMeasurement] Starting acquisition — "
            f"sample={self.config.sample_id}, "
            f"daq={self.config.daq_name}, "
            f"waveform={self.config.waveform}, "
            f"freq={self.config.signal_freq} Hz, "
            f"amplitude={self.config.amplitude} V"
        )

        data = self.acquire()

        save_path = None
        if self.config.save_to_file:
            save_path = self.save(data)

        if self.config.plot:
            self.plot(data)

        return {**data, "save_path": save_path}


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------
def run_pund(config: PUNDConfig) -> dict:
    """
    One-liner to instantiate :class:`PUNDMeasurement` and run it.

    Parameters
    ----------
    config : PUNDConfig
        Measurement configuration object.

    Returns
    -------
    dict
        ``{"time_ms", "ao", "ai", "save_path"}``

    Examples
    --------
    >>> from flex.exp.pund import PUNDMeasurement, PUNDConfig, run_pund
    >>> results = run_pund(PUNDConfig(
    ...     sample_id="SA40001",
    ...     amplitude=5.0,
    ...     waveform="triangle",
    ...     save_to_file=True,
    ...     save_path=r"C:\\Data\\PUND",
    ... ))
    """
    return PUNDMeasurement(config).run()