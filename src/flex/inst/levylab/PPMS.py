from flex.inst.base import Instrument
from flex.inst.levylab.types.Temperature import Temperature
from flex.inst.levylab.types.Magnet import Magnet
import os

_DEFAULT_ADDRESS = "tcp://localhost:29270"
_LABVIEW_CLASS_NAME = "instrument.PPMS.lvclass"

logpath = os.path.join(os.environ.get("LOCALAPPDATA"), "Levylab", "FLEX", "logs")
os.makedirs(logpath, exist_ok=True)


class PPMS(Instrument, Temperature, Magnet):
    """PPMS driver with Temperature and Magnet capabilities."""

    def __init__(self, address: str = _DEFAULT_ADDRESS):
        super().__init__(address, log_file=os.path.join(logpath, "PPMS.log"))

    # --------- Optional overrides (only if different from default) ---------
    # For standard PPMS, the default ZMQ commands in Temperature and Magnet work,
    # so no override is strictly necessary.

    # Example: override only if your instrument behaves differently:
    # def set_temperature(self, temperature: float, rate: float, channel: int = 0):
    #     self._send_command("setTempCustom", {"target": temperature, "rate": rate, "ch": channel})

    # instrument-specific commands
    def get_LHe_level(self) -> float:
        return self._send_command("getLHeLevel")["result"]
    
if __name__ == '__main__':
    ppms = PPMS()
    ppms.help()
    ppms.getTemperature()
    ppms.close()