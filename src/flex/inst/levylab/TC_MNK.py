'''
Levylab FLEX instrument driver for Levylab CF900 - Leiden TC (AVS47B)
<https://github.com/levylabpitt/Leiden-FP-and-TC>

Authors:
Pubudu Wijesinghe <pubudu.wijesinghe@levylab.org>

Contact an author for any queries.
'''

from flex.inst.base import Instrument
from flex.inst.levylab.types.Temperature import Temperature
import os

# Default addresses for the subsystems
_DEFAULT_ADDRESS_TEMP = 'tcp://10.226.177.244:10024' 
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
    
    def getHeater(self, channel):
        cmd = 'getHeater'
        params = [channel]
        response = self._send_command(cmd, params)
        return response['result']




if __name__ == "__main__":
    # Test the Oxford MNK Instrument Class
    mnk = TC_MNK()
    print(f"Magnetic field: {mnk.getMagnet()}")
    # print(f"LN2Level: {mnk.getLN2Level()}")
    print(f"Temperature (ch 0): {mnk.getTemperature(channel=0)}")
    print(f"Heater (ch 0): {mnk.getHeater(channel=0)}")
    mnk.close()