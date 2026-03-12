from abc import ABC, abstractmethod

class Magnet:
    """Standard Magnet capability for Levylab IF Instruments."""

    @abstractmethod
    def setMagnet(self, field: float, rate: float, axis: str = "Z", mode: str = "Persistent"):
        """
        Default ZMQ command to set magnetic field.
        """
        self._send_command("setMagnet", {
            "field": field,
            "rate": rate,
            "axis": axis,
            "mode": mode
        })

    @abstractmethod
    def getMagnet(self) -> float:
        """
        Default ZMQ command to get magnetic field.
        """
        return self._send_command("getMagnet")["result"]

    def getMagnetTarget(self) -> float:
        """
        Default ZMQ command to get magnetic field.
        Override in child if instrument uses different RPC commands.
        """
        return self._send_command("getMagnetTarget", ['Z'])["result"]
