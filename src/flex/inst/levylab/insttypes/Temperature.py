from abc import ABC, abstractmethod

class Temperature(ABC):
    """Standard Temperature capability for Levylab IF Instruments."""

    @abstractmethod
    def setTemperature(self, temperature: float, rate: float, channel: int = 0):
        """
        Default ZMQ command to set temperature.
        """
        self._send_command("setTemperature", {
            "temperature": temperature,
            "rate": rate,
            "channel": channel
        })

    @abstractmethod
    def getTemperature(self, channel: int = 0) -> dict:
        """
        Default ZMQ command to get temperature.
        """
        return self._send_command("getTemperature", [channel])["result"]
    
    def getTemperatureTarget(self, channel: int = 0) -> dict:
        """
        Default ZMQ command to get temperature target.
        """
        return self._send_command("getTemperatureTarget", [channel])["result"]
