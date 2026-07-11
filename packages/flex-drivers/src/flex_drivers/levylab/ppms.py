"""Quantum Design PPMS driver (LevyLab Instrument Framework app).

FLEX v1's five behaviorally identical variants are consolidated into this
single :class:`PPMS` class; pass the address of the instance you want to
talk to:

===========  =========================  ================================
v1 class     default address            LabVIEW class
===========  =========================  ================================
``PPMS``     ``tcp://localhost:29270``  ``instrument.PPMS.lvclass``
``PPMS1``    ``tcp://localhost:29171``  ``instrument.PPMS1.lvclass``
``PPMS2``    ``tcp://localhost:29172``  ``instrument.PPMS2.lvclass``
``PPMS3``    ``tcp://localhost:29173``  ``instrument.PPMS3.lvclass``
``PPMSW1``   ``tcp://localhost:29175``  ``instrument.PPMS-W-1.lvclass``
===========  =========================  ================================

The variant LabVIEW class names are kept in :attr:`PPMS.lv_class_aliases` so
CESession auto-discovery still resolves them to this driver.

Conforms to ``flex_drivers.levylab.capabilities.Temperature`` and ``Magnet``.
"""

from __future__ import annotations

from typing import Any

from flex_drivers.levylab._commands import IFMagnetCommands, IFTemperatureCommands
from flex_protocols import ZMQInstrument


class PPMS(ZMQInstrument, IFTemperatureCommands, IFMagnetCommands):
    """PPMS driver with Temperature and Magnet capabilities."""

    lv_class = "instrument.PPMS.lvclass"
    lv_class_aliases: tuple[str, ...] = (
        "instrument.PPMS1.lvclass",
        "instrument.PPMS2.lvclass",
        "instrument.PPMS3.lvclass",
        "instrument.PPMS-W-1.lvclass",
    )

    def __init__(self, name: str = "ppms", address: str = "tcp://localhost:29270", **kwargs):
        super().__init__(name, address, **kwargs)
        self.add_parameter("temperature", getter=self.get_temperature, unit="K")
        self.add_parameter("field", getter=self.get_magnet, unit="T")

    def get_lhe_level(self) -> Any:
        """Read the liquid-helium level (IF ``getLHeLevel``)."""
        return self.call("getLHeLevel")
