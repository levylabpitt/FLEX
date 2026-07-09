"""Colby Instruments programmable delay line (PDL) over VISA/GPIB."""

from __future__ import annotations

import time

from flex_protocols import VISAInstrument


class ColbyPDL(VISAInstrument):
    """Colby Instruments programmable delay line.

    On connect the driver reads the stepper rate (``RATE?``) and re-sends it
    before each :meth:`set_delay` unless an explicit rate is given.
    """

    def __init__(
        self,
        name: str = "pdl",
        resource: str = "",
        *,
        timeout: float = 5.0,
        backend: str = "",
        **kwargs,
    ):
        """
        Args:
            name: Instrument name used in logs, snapshots, and experiments.
            resource: VISA resource string, e.g. ``"GPIB1::15::INSTR"``.
            timeout: Seconds to wait for responses.
            backend: Optional VISA library spec.
        """
        super().__init__(name, resource, timeout=timeout, backend=backend, **kwargs)
        self._stepper_rate = self.query("RATE?")
        self.add_parameter(
            "delay",
            getter=self.get_delay,
            setter=self.set_delay,
            doc="Delay setting (set in ns by default; get returns the raw reply).",
        )

    def set_delay(self, delay: float, unit: str = "ns", stepper_rate: float | None = None) -> None:
        """Set the delay.

        Args:
            delay: Delay value.
            unit: Delay unit string sent to the instrument (default ``"ns"``).
            stepper_rate: Optional stepper rate; defaults to the last rate used
                (initially the rate read from the instrument at connect).
        """
        rate = self._stepper_rate if stepper_rate is None else stepper_rate
        self._stepper_rate = rate
        self.write(f"RATE {rate}")
        time.sleep(1)
        self.write(f"DEL {delay} {unit}")

    def get_delay(self) -> str:
        """Get the current delay (raw instrument reply to ``DEL?``)."""
        return self.query("DEL?")
