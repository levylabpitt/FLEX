"""Leiden temperature controller drivers (LevyLab IF apps).

<https://github.com/levylabpitt/Leiden-FP-and-TC>

* :class:`TC_CF` — LevyLab CF900 - Leiden TC (Z Bridge)
* :class:`TC_MNK` — LevyLab MNK - Leiden TC (AVS47B)

Both are passive cooling systems: reading temperature and heater power is
supported, but ``set_temperature`` is deliberately disabled (manual gas
handling is required to change base temperature).
"""

from __future__ import annotations

from typing import Any

from flex_drivers.levylab._commands import IFTemperatureCommands
from flex_protocols import ZMQInstrument


class _LeidenTC(ZMQInstrument, IFTemperatureCommands):
    """Shared Leiden TC behavior (temperature/heater readout only)."""

    def set_temperature(
        self, setpoint: float, rate: float | None = None, *, channel: int = 0
    ) -> None:
        """Override to disable control for this specific hardware."""
        raise NotImplementedError(
            f"{type(self).__name__} is a passive cooling system. "
            "Manual gas handling is required to change base temperature."
        )

    def get_heater(self, channel: int) -> Any:
        """Read the heater output of ``channel`` (IF ``getHeater``)."""
        return self.call("getHeater", [channel])


class TC_CF(_LeidenTC):  # noqa: N801 (lab-known name)
    """Leiden TC (Z Bridge) on the CF900 fridge."""

    lv_class = "Inst.TC.CF.lvclass"

    def __init__(self, name: str = "tc_cf", address: str = "tcp://localhost:10025", **kwargs):
        super().__init__(name, address, **kwargs)


class TC_MNK(_LeidenTC):  # noqa: N801 (lab-known name)
    """Leiden TC (AVS47B) on the MNK fridge."""

    lv_class = "Inst.TC.MNK.lvclass"

    def __init__(self, name: str = "tc_mnk", address: str = "tcp://localhost:10024", **kwargs):
        super().__init__(name, address, **kwargs)
