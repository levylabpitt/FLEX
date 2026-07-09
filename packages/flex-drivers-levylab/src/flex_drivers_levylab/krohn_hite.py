"""LevyLab Krohn-Hite 7008 programmable amplifier driver.

<https://github.com/levylabpitt/Krohn-Hite-7008>

Port of FLEX v1 ``flex.inst.levylab.Krohn_Hite_7008`` (authors: Pubudu
Wijesinghe <pubudu.wijesinghe@levylab.org>, Aria Hajikhani
<aria.hajikhani@levylab.org>). Only the live v1 methods are ported; a large
block of commented-out per-parameter validation helpers in v1 was dropped.
"""

from __future__ import annotations

from typing import Any

from flex_protocols import ZMQInstrument


class KrohnHite7008(ZMQInstrument):
    """Krohn-Hite 7008 8-channel amplifier (LevyLab Instrument Framework app).

    Channel configuration dicts use the IF key spellings, e.g.::

        {"channel": 1, "gain": "10", "input": "DIFF", "shunt": "10M",
         "couple": "AC", "filter": "OFF"}
    """

    lv_class = "Inst.Krohn-Hite-7008.lvclass"

    def __init__(self, name: str = "kh7008", address: str = "tcp://localhost:29160", **kwargs):
        super().__init__(name, address, **kwargs)

    def set_kh_channel(self, config: list[dict]) -> None:
        """Configure several channels at once (IF ``setAllChannels``)."""
        self.call("setAllChannels", {"allChannelProperties": config})

    def set_kh_channel_single(self, config: list[dict]) -> None:
        """Configure a single channel (IF ``setChannel``)."""
        self.call("setChannel", {"allChannelProperties": config})

    def get_channel(self, channel: int) -> Any:
        """Read the configuration of one channel (IF ``getChannel``)."""
        return self.call("getChannel", {"channel": channel})
