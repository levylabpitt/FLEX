"""
FLEX driver for the Levylab Krohn-Hite 7008.

Provides channel read/write functions and convenient setters for
gain, input, shunt, coupling, and filter settings.

Authors:
    Pubudu Wijesinghe <pubudu.wijesinghe@levylab.org>
    Aria Hajikhani <aria.hajikhani@levylab.org>
"""

import os

from flex.inst.base import Instrument
from flex.inst.levylab.insttypes.Amplifier import Amplifier

_DEFAULT_ADDRESS = "tcp://localhost:29160"
_LABVIEW_CLASS_NAME = "Inst.Krohn-Hite-7008.lvclass"

logpath = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "Levylab",
    "FLEX",
    "logs",
)
os.makedirs(logpath, exist_ok=True)


class Krohn_Hite_7008(Instrument, Amplifier):
    """FLEX driver for the Krohn-Hite 7008."""

    def __init__(self, address=_DEFAULT_ADDRESS):
        super().__init__(
            address,
            log_file=os.path.join(logpath, "Krohn-Hite-7008.log"),
        )

    def getChannel(self, channel):
        """Return the configuration for one channel."""
        cmd = "getChannel"
        params = {"channel": channel}

        response = self._send_command(cmd, params)
        return response["result"]["allChannelProperties"][0]

    def getAllChannels(self):
        """Return the configuration for all channels."""
        cmd = "getAllChannels"
        params = {}

        response = self._send_command(cmd, params)
        return response["result"]["allChannelProperties"]

    def setChannel(self, config: dict):
        """
        Set a channel using a complete configuration dictionary.

        Note: The underlying FLEX/LabVIEW command is currently not working.
        """
        cmd = "setChannel"
        params = {"ChannelProperties": config}

        return self._send_command(cmd, params)

    def setChannelConfig(self, config: list):
        """Set all channel configurations."""
        cmd = "setAllChannels"
        params = {"allChannelProperties": config}

        return self._send_command(cmd, params)

    def getShuntResistor(self):
        """Return available shunt resistor information."""
        cmd = "getShuntResistor"
        params = {}

        response = self._send_command(cmd, params)
        return response["result"]["ShuntResistor"]

    def getChassis(self):
        """Return chassis information."""
        cmd = "getChassis"
        params = {}

        response = self._send_command(cmd, params)
        return response["result"]["Chassis"]

# ---------- Custom Functions ---------->

    def updateChannel(self, channel, **changes):
        """Update one or more properties of a channel."""
        config = self.getChannel(channel)
        config.update(changes)

        all_channels = self.getAllChannels()

        for i, channel_config in enumerate(all_channels):
            if channel_config["channel"] == channel:
                all_channels[i] = config
                break
        else:
            raise ValueError(f"Channel {channel} not found")

        return self.setChannelConfig(all_channels)

    def configureChannel(
        self,
        channel,
        gain=None,
        input_type=None,
        shunt=None,
        coupling=None,
        filter_enabled=None,
    ):
        """Set any combination of channel properties."""
        changes = {}

        if gain is not None:
            changes["gain"] = str(gain)

        if input_type is not None:
            changes["input"] = input_type

        if shunt is not None:
            changes["shunt"] = shunt

        if coupling is not None:
            changes["couple"] = coupling

        if filter_enabled is not None:
            changes["filter"] = "ON" if filter_enabled else "OFF"

        return self.updateChannel(channel, **changes)

    def setGain(self, channel, gain):
        """Set channel gain."""
        return self.updateChannel(channel, gain=str(gain))

    def setInput(self, channel, input_type):
        """Set channel input mode."""
        return self.updateChannel(channel, input=input_type)

    def setShunt(self, channel, shunt):
        """Set channel shunt resistance."""
        return self.updateChannel(channel, shunt=shunt)

    def setCoupling(self, channel, coupling):
        """Set channel coupling."""
        return self.updateChannel(channel, couple=coupling)

    def setFilter(self, channel, enabled):
        """Enable or disable the channel filter."""
        return self.updateChannel(
            channel,
            filter="ON" if enabled else "OFF",
        )

if __name__ == "__main__":
    kh = Krohn_Hite_7008()

    print(kh.getChannel(1))
    print(kh.getAllChannels())

    # Examples:
    #
    # kh.setGain(1, 100)
    # kh.setInput(1, "DIFF")
    # kh.setShunt(1, "10M")
    # kh.setCoupling(1, "DC")
    # kh.setFilter(1, False)
    #
    # Or change several settings at once:
    #
    kh.configureChannel(
        1,
        gain=100,
        input_type="DIFF",
        shunt="10M",
        coupling="DC",
        filter_enabled=False,
    )

    kh.close()
