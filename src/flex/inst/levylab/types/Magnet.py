

class Magnet:
    """Magnet capability with default ZMQ commands for instruments."""

    def setMagnet(self, field: float, rate: float, axis: str = "Z", mode: str = "Persistent"):
        """
        Default ZMQ command to set magnetic field.
        Override in child if instrument uses different RPC commands.
        """
        self._send_command("setMagnet", {
            "field": field,
            "rate": rate,
            "axis": axis,
            "mode": mode
        })

    def getMagnet(self) -> float:
        """
        Default ZMQ command to get magnetic field.
        Override in child if instrument uses different RPC commands.
        """
        return self._send_command("getMagnet")["result"]

    def getMagnetTarget(self) -> float:
        """
        Default ZMQ command to get magnetic field.
        Override in child if instrument uses different RPC commands.
        """
        return self._send_command("getMagnetTarget", ['Z'])["result"]
