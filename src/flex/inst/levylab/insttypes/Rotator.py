from abc import ABC, abstractmethod

class Rotator:
    """Standard Rotator capability for Levylab IF Instruments."""

    @abstractmethod
    def setAngle(self, angle: float, rate: float, channel:int = 0):
        """
        Default ZMQ command to set rotator angle.
        """
        cmd = "setAngle"
        params = {'angle': angle, 'rate': rate, 'channel': channel}
        self._send_command(cmd, params)

    @abstractmethod
    def getAngle(self) -> float:
        """
        Default ZMQ command to get rotator angle.
        """
        return self._send_command("getAngle")["result"]