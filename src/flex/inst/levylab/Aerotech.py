from flex.inst.base import Instrument
from flex.inst.levylab.insttypes.DelayLine import DelayLine
import os

_DEFAULT_ADDRESS = "tcp://localhost:XXXXX"
_LABVIEW_CLASS_NAME = "Instrument.Aerotech.lvclass"

logpath = os.path.join(os.environ.get("LOCALAPPDATA"), "Levylab", "FLEX", "logs")
os.makedirs(logpath, exist_ok=True)


class Aerotech(DelayLine):
    """Aerotech stage driver with DelayLine capabilities."""

    def __init__(self, address: str = _DEFAULT_ADDRESS):
        pass

    def help():
        raise NotImplementedError(
            f"Driver not available."
            )

    pass
    
    
if __name__ == '__main__':
    delay = Aerotech()
    delay.help()
    # cryo.getTemperature()
    # ppms.close()