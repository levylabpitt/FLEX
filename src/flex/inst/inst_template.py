from flex.inst.base import Instrument
from flex.inst.levylab.insttypes.Temperature import Temperature
from flex.inst.levylab.insttypes.Magnet import Magnet
import os

_DEFAULT_ADDRESS = "tcp://localhost:<port>"
_LABVIEW_CLASS_NAME = "<lvclassname>.lvclass"

logpath = os.path.join(os.environ.get("LOCALAPPDATA"), "Levylab", "FLEX", "logs")
os.makedirs(logpath, exist_ok=True)

# NOTE: Class should have the same name as the module name
class inst_template(Instrument, Temperature, Magnet):
    """FLEX Driver for a Levylab Instrument Framework Instrument"""

    def __init__(self, address: str = _DEFAULT_ADDRESS):
        super().__init__(address, log_file=os.path.join(logpath, "<inst_template>.log"))

    # --------- Optional overrides (only if different from default) ---------
    # For standard PPMS, the default ZMQ commands in Temperature and Magnet work,
    # so no override is strictly necessary.

    # Example: override only if your instrument behaves differently:
    # def set_temperature(self, temperature: float, rate: float, channel: int = 0):
    #     self._send_command("setTempCustom", {"target": temperature, "rate": rate, "ch": channel})

    # instrument-specific commands
    def get_LHe_level(self) -> float:
        return self._send_command("getLHeLevel")["result"]

# Test the class    
if __name__ == '__main__':
    inst = inst_template()
    inst.help()
    inst.close()