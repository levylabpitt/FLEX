from flex.inst.base import Instrument
from flex.inst.levylab.insttypes.Temperature import Temperature
import os

_DEFAULT_ADDRESS = "tcp://localhost:55446"
_LABVIEW_CLASS_NAME = "instrument.Cryostation.lvclass"

logpath = os.path.join(os.environ.get("LOCALAPPDATA"), "Levylab", "FLEX", "logs")
os.makedirs(logpath, exist_ok=True)


class Cryostation(Instrument, Temperature):
    """Montana Cryostation driver with Temperature capabilities."""

    def __init__(self, address: str = _DEFAULT_ADDRESS):
        super().__init__(address, log_file=os.path.join(logpath, "Cryostation.log"))

    def getTemperature(self, channel = 0):
        """
        channel 0: Sample Temperature
        channel 1: Platform Temperature
        channel 2: Stage 1 Temperature
        channel 3: Stage 2 Temperature
        """
        return super().getTemperature(channel)
    
    def setTemperature(self, temperature, rate, channel = 0):
        """Override to disable control for this specific hardware."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support setTemperature"
        )
    
    def getTemperatureTarget(self, channel = 0):
        return super().getTemperatureTarget(channel)
    
    
if __name__ == '__main__':
    cryo = Cryostation()
    cryo.help()
    # cryo.getTemperature()
    # ppms.close()