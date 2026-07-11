"""Montana Instruments Cryostation driver (LevyLab Instrument Framework app).

Port of FLEX v1 ``flex.inst.levylab.Cryostation``. Read-only temperature:
v1 deliberately disabled ``setTemperature`` for this hardware.
"""

from __future__ import annotations

from typing import Any

from flex_drivers.levylab._commands import IFTemperatureCommands
from flex_protocols import ZMQInstrument


class Cryostation(ZMQInstrument, IFTemperatureCommands):
    """Montana Cryostation driver with Temperature capabilities."""

    lv_class = "instrument.Cryostation.lvclass"

    def __init__(self, name: str = "cryostation", address: str = "tcp://localhost:55446", **kwargs):
        super().__init__(name, address, **kwargs)
        self.add_parameter("temperature", getter=self.get_temperature, unit="K")

    def get_temperature(self, channel: int = 0) -> Any:
        """Read a temperature channel.

        channel 0: Sample Temperature
        channel 1: Platform Temperature
        channel 2: Stage 1 Temperature
        channel 3: Stage 2 Temperature
        """
        return super().get_temperature(channel)

    def set_temperature(
        self, setpoint: float, rate: float | None = None, *, channel: int = 0
    ) -> None:
        """Override to disable control for this specific hardware."""
        raise NotImplementedError(f"{type(self).__name__} does not support set_temperature")
