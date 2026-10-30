"""LevyLab Krohn-Hite 7008 programmable amplifier driver.

<https://github.com/levylabpitt/Krohn-Hite-7008>
"""

from __future__ import annotations

from typing import Any

from flex.protocols import ZMQInstrument


class KrohnHite7008(ZMQInstrument):
    """Krohn-Hite 7008 8-channel amplifier (LevyLab Instrument Framework app).

    Channel configuration dicts use the IF key spellings, e.g.::

        {"channel": 1, "gain": "10", "input": "DIFF", "shunt": "10M",
         "couple": "AC", "filter": "OFF"}
    """

    lv_class = "Inst.Krohn-Hite-7008.lvclass"

    def __init__(self, name: str = "kh7008", address: str = "tcp://localhost:29160", **kwargs):
        super().__init__(name, address, **kwargs)

    def get_channel(self, channel: int) -> dict:
        """Configuration of one channel."""
        return self.call("getChannel", {"channel": channel})["allChannelProperties"][0]

    def get_all_channels(self) -> list[dict]:
        """Configuration of every channel."""
        return self.call("getAllChannels", {})["allChannelProperties"]

    def set_channel(self, config: dict) -> Any:
        """Set one channel from a complete configuration dict.

        The IF app's ``setChannel`` is currently broken; use ``update_channel``.
        """
        return self.call("setChannel", {"ChannelProperties": config})

    def set_channel_config(self, config: list[dict]) -> Any:
        """Set the configuration of all channels (IF ``setAllChannels``)."""
        return self.call("setAllChannels", {"allChannelProperties": config})

    def get_shunt_resistor(self) -> Any:
        return self.call("getShuntResistor", {})["ShuntResistor"]

    def get_chassis(self) -> Any:
        return self.call("getChassis", {})["Chassis"]

    # -- custom functions -----------------------------------------------------

    def update_channel(self, channel: int, **changes: Any) -> Any:
        """Change some properties of one channel and leave the rest as they are."""
        channels = self.get_all_channels()
        for i, current in enumerate(channels):
            if current["channel"] == channel:
                channels[i] = {**current, **changes}
                return self.set_channel_config(channels)
        raise ValueError(f"Channel {channel} not found")

    def set_gain(self, channel: int, gain: int) -> Any:
        return self.update_channel(channel, gain=str(gain))

    def set_input(self, channel: int, input_type: str) -> Any:
        """``OFF``, ``SE+``, ``SE-`` or ``DIFF``."""
        return self.update_channel(channel, input=input_type)

    def set_shunt(self, channel: int, shunt: int | str) -> Any:
        return self.update_channel(channel, shunt=shunt)

    def set_coupling(self, channel: int, coupling: str) -> Any:
        """``AC`` or ``DC``."""
        return self.update_channel(channel, couple=coupling)

    def set_filter(self, channel: int, enabled: bool) -> Any:
        return self.update_channel(channel, filter="ON" if enabled else "OFF")
