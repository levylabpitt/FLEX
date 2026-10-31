"""Quantum Design OptiCool (LevyLab IF app); conforms to the Temperature and Magnet capabilities."""

from __future__ import annotations

from typing import Any

from flex.protocols import ZMQInstrument
from flex_drivers.levylab._commands import IFMagnetCommands, IFTemperatureCommands


class Opticool(ZMQInstrument, IFTemperatureCommands, IFMagnetCommands):
    """Opticool driver with Temperature and Magnet capabilities."""

    lv_class = "instrument.OptiCool.lvclass"

    def __init__(self, name: str = "opticool", address: str = "tcp://localhost:29174", **kwargs):
        super().__init__(name, address, **kwargs)
        self.add_parameter("temperature", getter=self.get_temperature, unit="K")
        self.add_parameter("field", getter=self.get_field, unit="T")

    def get_lhe_level(self) -> Any:
        """Read the liquid-helium level (IF ``getLHeLevel``)."""
        return self.call("getLHeLevel")
