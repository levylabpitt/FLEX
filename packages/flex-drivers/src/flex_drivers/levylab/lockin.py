"""LevyLab Multichannel Lock-in driver.

<https://github.com/levylabpitt/Multichannel-Lockin>

Conforms to ``flex_drivers.levylab.capabilities.DAQ`` (``get_ai`` / ``set_ao``,
where ``set_ao`` drives the DC offset of the output channel).
"""

from __future__ import annotations

import time
from typing import Any

from flex.protocols import ZMQInstrument

_ALLOWED_AO_FUNCTIONS = {"Sine", "Triangle", "Square"}


class Lockin(ZMQInstrument):
    """Multichannel lock-in amplifier (LevyLab Instrument Framework app)."""

    lv_class = "Instrument.Lockin.lvclass"

    def __init__(self, name: str = "lockin", address: str = "tcp://localhost:29170", **kwargs):
        super().__init__(name, address, **kwargs)
        self.add_parameter("state", getter=self.get_state, doc="Lock-in state machine state")

    def get_ao(self, channel: int) -> Any:
        """Read the analog output configuration of ``channel``."""
        return self.call("getAO", {"channel": channel})

    def get_ai(self, channel: int) -> Any:
        """Read the analog input of ``channel``."""
        return self.call("getAI", {"channel": channel})

    def set_ao_amplitude(self, channel: int, value: float) -> None:
        self.call("setAO_Amplitude", {"Channel": channel, "Amplitude": value})

    def set_ao_dc(self, channel: int, value: float) -> None:
        self.call("setAO_DC", {"Channel": channel, "DC": value})

    def set_ao_frequency(self, channel: int, value: float) -> None:
        self.call("setAO_Frequency", {"Channel": channel, "Frequency": value})

    def set_ao_phase(self, channel: int, value: float) -> None:
        self.call("setAO_Phase", {"Channel": channel, "Phase": value})

    def set_ao_function(self, channel: int, value: str) -> None:
        """Set the AO waveform: Sine, Triangle, or Square."""
        if value not in _ALLOWED_AO_FUNCTIONS:
            raise ValueError(
                f"Invalid value: {value}. Allowed values are: {', '.join(_ALLOWED_AO_FUNCTIONS)}"
            )
        self.call("setAO_Function", {"Channel": channel, "Function": value})

    def set_ref_frequency(self, channel: int, value: float) -> None:
        self.call("setREF_Frequency", {"Channel": channel, "Frequency": value})

    def set_ref_phase(self, channel: int, value: float) -> None:
        self.call("setREF_Phase", {"Channel": channel, "Phase": value})

    def set_ref_tc(self, channel: int, value: float) -> None:
        """Set the time constant of reference ``channel``."""
        self.call("setREF_TC", {"Channel": channel, "TC": value})

    def set_ref_roll_off(self, channel: int, value: float) -> None:
        self.call("setREF_Roll-Off", {"Channel": channel, "Roll-Off": value})

    def get_input_gain(self) -> list:
        """Gains of the AI channels, one per channel in channel order."""
        return self.call("getInputGain")

    def set_input_gain(self, gains: list) -> None:
        """Set every AI gain at once; the app takes the bare list. To change one
        channel, edit that index of ``get_input_gain()`` and write the list back."""
        self.call("setInputGain", list(gains))

    def get_output_gain(self) -> list:
        """Gains of the AO channels, one per channel in channel order."""
        return self.call("getOutputGain")

    def set_output_gain(self, gains: list) -> None:
        """Set every AO gain at once (see ``set_input_gain``)."""
        self.call("setOutputGain", list(gains))

    def get_results(self) -> dict:
        return self.call("getResults")

    def set_state(self, value: str) -> None:
        self.call("setState", {"State": value})

    def get_state(self) -> str:
        return self.call("getState")

    def set_sweep_time(self, value: float) -> None:
        self.call("setSweep_Time", {"SweepTime": value})

    def set_sampling_mode(self, value: str) -> None:
        """Set the sampling mode (IF method ``setSamplingFsMode``)."""
        self.call("setSamplingFsMode", value)

    def get_sampling_mode(self) -> Any:
        return self.call("getSamplingFsMode")

    def get_sweep_waveforms(self) -> dict:
        return self.call("getSweepWaveforms")

    def set_sweep(self, sweep_config: dict) -> None:
        """Configure a sweep.

        sweep_config format::

            sweep_config = {"sweepTime": sweep_time,
                            "initialWaitTime": 2,
                            "returnToStart": False,
                            "sweepChannels": [{"Enable?": True,
                                               "Channel": channel,
                                               "Start": start,
                                               "End": stop,
                                               "Pattern": "Ramp /",
                                               "Table": []},
                                              ]}
        """
        self.call("setSweep", sweep_config)

    # -- capabilities.DAQ -----------------------------------------------------

    def set_ao(self, channel: int, value: float) -> None:
        """Canonical DAQ capability alias: set the DC value of an AO channel."""
        self.set_ao_dc(channel, value)

    # -- custom functions -----------------------------------------------------

    @staticmethod
    def _result_key(channel: int, param: str, ref: int) -> str:
        return f"AI{channel}.{param}" if param == "Mean" else f"AI{channel}.Ref{ref}.{param}"

    def get_lockin_result(self, channel: int, param: str, ref: int = 1) -> float | None:
        """Extract one value (e.g. ``X``, ``Theta``, ``Mean``) from ``getResults``."""
        return self.get_lockin_results(channel, (param,), ref)[param]

    def get_lockin_results(
        self, channel: int, params: tuple[str, ...] = ("X", "Y", "R", "Theta"), ref: int = 1
    ) -> dict[str, float | None]:
        """Several values from a single ``getResults`` call, so they share one acquisition."""
        results = self.get_results()["Results (Dictionary)"]
        by_key = {item["key"]: item["value"] for item in results}
        return {p: by_key.get(self._result_key(channel, p, ref)) for p in params}

    def lockin_sweep(self, sweep_config: dict, timeout: float = 10) -> None:
        """Run a sweep and block until it finishes."""
        state = self.get_state()
        if state == "sweeping":
            raise RuntimeError("Request Denied! Already sweeping")
        if state == "idle":
            self.set_state("start")
        self.set_sweep(sweep_config)
        time.sleep(0.5)
        self.set_state("start sweep")
        wait_time = sweep_config["sweepTime"] + sweep_config["initialWaitTime"]
        time.sleep(wait_time)
        start_time = time.time()
        while self.get_state() == "sweeping":
            if time.time() - start_time > timeout:
                raise TimeoutError(
                    f"Sweep operation timed out after {timeout} seconds. "
                    "Please check the Multichannel Lock-in Application."
                )
            time.sleep(0.5)

    def set_backgate(
        self,
        bg_channel: int,
        bg_target: float,
        sweep_rate: float,
        initial_wait: float = 1,
        tol: float = 1e-3,
    ) -> None:
        """Sweep the backgate voltage to a target value.

        Args:
            bg_channel: Analog output channel used for the backgate.
            bg_target: Target backgate voltage in volts (V).
            sweep_rate: Sweep rate in seconds per volt (s/V).
            initial_wait: Delay before starting the sweep in seconds. Default 1 s.
            tol: Voltage tolerance in volts used to determine whether the gate
                is already at the target voltage. Default 1e-3 V.
        """
        current_bg = self.get_ao(bg_channel)[bg_channel - 1]["Y"][0]

        # Skip sweep if already at target
        if abs(bg_target - current_bg) < tol:
            self.log.info("Backgate already at %.2f V. Target is within tolerance.", bg_target)
            return

        duration = abs(bg_target - current_bg) * sweep_rate
        self.log.info("Sweeping backgate from %.2f to %.2f V...", current_bg, bg_target)

        sweep_config = {
            "sweepTime": duration,
            "initialWaitTime": initial_wait,
            "returnToStart": False,
            "sweepChannels": [
                {
                    "Enable?": True,
                    "Channel": bg_channel,
                    "Start": current_bg,
                    "End": bg_target,
                    "Pattern": "Ramp /",
                    "Table": [],
                },
            ],
        }
        self.lockin_sweep(sweep_config)
