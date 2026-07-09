"""Quantum Design OptiCool driver (LevyLab Instrument Framework app).

Port of FLEX v1 ``flex.inst.levylab.Opticool``. Conforms to
``flex.instrument.capabilities.Temperature`` and ``Magnet``.
"""

from __future__ import annotations

from typing import Any

from flex_drivers_levylab._commands import IFMagnetCommands, IFTemperatureCommands
from flex_protocols import ZMQInstrument


class Opticool(ZMQInstrument, IFTemperatureCommands, IFMagnetCommands):
    """Opticool driver with Temperature and Magnet capabilities."""

    lv_class = "instrument.OptiCool.lvclass"

    def __init__(self, name: str = "opticool", address: str = "tcp://localhost:29174", **kwargs):
        super().__init__(name, address, **kwargs)
        self.add_parameter("temperature", getter=self.get_temperature, unit="K")
        self.add_parameter("field", getter=self.get_magnet, unit="T")

    # Level type not defined yet
    def get_lhe_level(self) -> Any:
        """Read the liquid-helium level (IF ``getLHeLevel``)."""
        return self.call("getLHeLevel")
