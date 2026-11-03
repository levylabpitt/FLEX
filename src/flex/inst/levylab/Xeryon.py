"""
FLEX driver for the Xeryon Rotator.

Authors:
    Pubudu Wijesinghe <pubudu.wijesinghe@levylab.org>
"""

import os

from flex.inst.base import Instrument
from flex.inst.levylab.insttypes.Rotator import Rotator
from typing import Literal
import time

_DEFAULT_ADDRESS = "tcp://localhost:20001"
_LABVIEW_CLASS_NAME = "Inst.Xeryon-Rotator.lvclass"

logpath = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "Levylab",
    "FLEX",
    "logs",
)
os.makedirs(logpath, exist_ok=True)


class Xeryon(Instrument, Rotator):
    """FLEX driver for the Xeryon Rotator."""

    def __init__(self, address=_DEFAULT_ADDRESS):
        super().__init__(
            address,
            log_file=os.path.join(logpath, "Xeryon.log"),
        )

    def getAngle(self):
        """Return the current stage Angle."""
        cmd = "getAngle"
        params = {}

        response = self._send_command(cmd, params)
        return response["result"]

    def setAngle(self, angle_deg, rate):
        """Set the stage angle"""
        cmd = "setAngle"
        params = {'angle': angle_deg, 'rate': rate, 'channel': 0}

        self._send_command(cmd, params)

    def setState(self, state: Literal["Scan Left", "Scan Right", "Stop"]):
        """Set the state configuration."""
        valid_states = ("Scan Left", "Scan Right", "Stop")

        if state not in valid_states:
            raise ValueError(f"state must be one of {valid_states}")
        
        cmd = "setState"
        params = [state]

        self._send_command(cmd, params)

# -------------- Custom functions ---------------->

    def setAngleAndWait(self, angle, rate, tolerance=0.001):
        if self.getAngle()['finished'] and abs(self.getAngle()['angle'] - angle) < tolerance:
            return

        self.setAngle(angle, rate)

        while self.getAngle()['finished']:
            time.sleep(0.1)

        while not (status := self.getAngle())['finished']:
            print(f"Moving... Current angle: {status['angle']:.2f} deg", end='\r', flush=True)
            time.sleep(0.1)

        print(f"Angle set to {angle} deg.{' ' * 20}")

if __name__ == "__main__":
    rot = Xeryon()
    print(rot.help())
    rot.close()
