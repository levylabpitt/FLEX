"""Oxford Instruments magnet controller drivers (LevyLab IF apps).

* :class:`Oxford1820` — LevyLab MNK - OI1820
  <https://github.com/levylabpitt/Oxford-1820>
* :class:`OxfordVRM` — LevyLab CF900 - OIVRM
  <https://github.com/levylabpitt/Oxford-VRM>

Port of FLEX v1 ``flex.inst.levylab.Oxford1820`` and ``OxfordVRM`` (author:
Pubudu Wijesinghe <pubudu.wijesinghe@levylab.org>). Both conform to
``flex.instrument.capabilities.Magnet``.
"""

from __future__ import annotations

from flex_drivers_levylab._commands import IFMagnetCommands
from flex_protocols import ZMQInstrument


class Oxford1820(ZMQInstrument, IFMagnetCommands):
    """Oxford 1820 Magnet subsystem (MNK fridge)."""

    lv_class = "Instrument.Oxford1820.lvclass"

    def __init__(self, name: str = "oxford1820", address: str = "tcp://localhost:21212", **kwargs):
        super().__init__(name, address, **kwargs)
        self.add_parameter("field", getter=self.get_magnet, unit="T")


class OxfordVRM(ZMQInstrument, IFMagnetCommands):
    """Oxford VRM Magnet subsystem (CF900 fridge).

    v1 note: "Not intended for direct use - use MNK class instead."
    """

    lv_class = "Instrument.OxfordVRM.lvclass"

    def __init__(self, name: str = "oxford_vrm", address: str = "tcp://localhost:21213", **kwargs):
        super().__init__(name, address, **kwargs)
        self.add_parameter("field", getter=self.get_magnet, unit="T")
