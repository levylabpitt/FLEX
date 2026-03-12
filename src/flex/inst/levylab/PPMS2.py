from flex.inst.base import Instrument
from flex.inst.levylab.insttypes.Temperature import Temperature
from flex.inst.levylab.insttypes.Magnet import Magnet
import os

_DEFAULT_ADDRESS = "tcp://localhost:29172"
_LABVIEW_CLASS_NAME = "instrument.PPMS2.lvclass"

logpath = os.path.join(os.environ.get("LOCALAPPDATA"), "Levylab", "FLEX", "logs")
os.makedirs(logpath, exist_ok=True)


class PPMS2(Instrument, Temperature, Magnet):
    """PPMS driver with Temperature and Magnet capabilities."""

    def __init__(self, address: str = _DEFAULT_ADDRESS):
        super().__init__(address, log_file=os.path.join(logpath, "PPMS2.log"))

    def getTemperature(self, channel = 0):
        return super().getTemperature(channel)
    
    def setTemperature(self, temperature, rate, channel = 0):
        return super().setTemperature(temperature, rate, channel)
    
    def getTemperatureTarget(self, channel = 0):
        return super().getTemperatureTarget(channel)
    
    def getMagnet(self):
        return super().getMagnet()
    
    def setMagnet(self, field, rate, axis = "Z", mode = "Persistent"):
        return super().setMagnet(field, rate, axis, mode)
    
    def getMagnetTarget(self):
        return super().getMagnetTarget()

    # Level type not defined yet
    def get_LHe_level(self) -> float:
        return self._send_command("getLHeLevel")["result"]
    
if __name__ == '__main__':
    ppms = PPMS2()
    ppms.help()
    ppms.getTemperature()
    # ppms.close()