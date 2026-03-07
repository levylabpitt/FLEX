'''
Levylab FLEX instrument driver for Levylab CF900 - Leiden TC (Z Bridge)
<https://github.com/levylabpitt/Leiden-FP-and-TC>

Authors:
Pubudu Wijesinghe <pubudu.wijesinghe@levylab.org>

Contact an author for any queries.
'''

from flex.inst.base import Instrument
from flex.inst.levylab.types.Temperature import Temperature
import os

# Default addresses for the subsystems
_DEFAULT_ADDRESS_TEMP = 'tcp://10.226.177.219:10025'
_LABVIEW_CLASS_NAME = "Inst.TC.CF.lvclass"

# Path to the log file
logpath = os.path.join(os.environ.get('LOCALAPPDATA'), 'Levylab', 'FLEX', 'logs')
os.makedirs(logpath, exist_ok=True)

class TC_CF(Instrument, Temperature):
    '''
    Internal: Leiden Temperature subsystem.
    Not intended for direct use - use MNK class instead.
    '''
    def __init__(self, address=_DEFAULT_ADDRESS_TEMP):
        super().__init__(address, log_file=os.path.join(logpath, "TC_CF.log"))
    
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