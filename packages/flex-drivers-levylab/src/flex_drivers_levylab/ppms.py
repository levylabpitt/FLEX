"""Quantum Design PPMS driver (LevyLab Instrument Framework app).

Port of FLEX v1 ``flex.inst.levylab.PPMS``. v1 shipped five byte-for-byte
behaviorally identical variants (``PPMS``, ``PPMS1``, ``PPMS2``, ``PPMS3``,
``PPMSW1``) that differed ONLY in class name, default address, LabVIEW class
name, and log-file name (``PPMSW1`` even logged to ``PPMS3.log`` — a v1
copy-paste bug). v2 consolidates them into this single :class:`PPMS` class;
pass the address of the instance you want to talk to:

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

Conforms to ``flex.instrument.capabilities.Temperature`` and ``Magnet``.
"""

from __future__ import annotations

from typing import Any

from flex_protocols import ZMQInstrument

from flex_drivers_levylab._commands import IFMagnetCommands, IFTemperatureCommands


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

    # Level type not defined yet
    def get_lhe_level(self) -> Any:
        """Read the liquid-helium level (IF ``getLHeLevel``)."""
        return self.call("getLHeLevel")
