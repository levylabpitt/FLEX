'''
Levylab FLEX instrument driver for Levylab CF900 - Leiden TC (AVS47B)
<https://github.com/levylabpitt/Leiden-FP-and-TC>

Authors:
Pubudu Wijesinghe <pubudu.wijesinghe@levylab.org>

Contact an author for any queries.
'''

from flex.inst.base import Instrument
from flex.inst.levylab.insttypes.Temperature import Temperature
import os

# Default addresses for the subsystems
_DEFAULT_ADDRESS_TEMP = 'tcp://localhost:10024' 
_LABVIEW_CLASS_NAME = "Inst.TC.MNK.lvclass"

# Path to the log file
logpath = os.path.join(os.environ.get('LOCALAPPDATA'), 'Levylab', 'FLEX', 'logs')
os.makedirs(logpath, exist_ok=True)


class TC_MNK(Instrument, Temperature):
    '''
    Internal: Leiden TC (AVS47B) subsystem.
    '''
    def __init__(self, address=_DEFAULT_ADDRESS_TEMP):
          super().__init__(address, log_file=os.path.join(logpath, "TC_MNK.log"))
    
    def getTemperature(self, channel):
        cmd = 'getTemperature'
        params = [channel]
        response = self._send_command(cmd, params)
        return response['result']

    def setTemperature(self, *args, **kwargs):
            """Override to disable control for this specific hardware."""
            raise NotImplementedError(
                f"{self.__class__.__name__} is a passive cooling system. "
                "Manual gas handling is required to change base temperature."
            )

    def getHeater(self, channel):
        cmd = 'getHeater'
        params = [channel]
        response = self._send_command(cmd, params)
        return response['result']


if __name__ == "__main__":
    # Test the Oxford MNK Instrument Class
    mnk = TC_MNK()
    # print(f"LN2Level: {mnk.getLN2Level()}")
    print(f"Temperature (ch 0): {mnk.getTemperature(channel=0)}")
    print(f"Heater (ch 0): {mnk.getHeater(channel=0)}")
    # mnk.close()