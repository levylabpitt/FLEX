

class Temperature:
    """Temperature capability with default ZMQ commands for instruments."""

    def setTemperature(self, temperature: float, rate: float, channel: int = 0):
        """
        Default ZMQ command to set temperature.
        Override in child if instrument uses different RPC commands.
        """
        self._send_command("setTemperature", {
            "temperature": temperature,
            "rate": rate,
            "channel": channel
        })

    def getTemperature(self) -> dict:
        """
        Default ZMQ command to get temperature.
        Override in child if instrument uses different RPC commands.
        """
        return self._send_command("getTemperature")["result"]
