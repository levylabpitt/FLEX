'''
Levylab FLEX instrument driver for Levylab CF900 - OIVRM
<https://github.com/levylabpitt/Oxford-VRM>

Authors:
Pubudu Wijesinghe <pubudu.wijesinghe@levylab.org>

Contact an author for any queries.
'''

from flex.inst.base import Instrument
from flex.inst.levylab.types.Magnet import Magnet
import os

# Default addresses for the subsystems
_DEFAULT_ADDRESS_MAGNET = 'tcp://localhost:21213'
_LABVIEW_CLASS_NAME = "Instrument.OxfordVRM.lvclass"

# Path to the log file
logpath = os.path.join(os.environ.get('LOCALAPPDATA'), 'Levylab', 'FLEX', 'logs')
os.makedirs(logpath, exist_ok=True)


class OxfordVRM(Instrument, Magnet):
    '''
    Internal: Oxford VRM Magnet subsystem.
    Not intended for direct use - use MNK class instead.
    '''
    def __init__(self, address=_DEFAULT_ADDRESS_MAGNET):
        super().__init__(address, log_file=os.path.join(logpath, "OxfordVRM.log"))

    def getMagnet(self):
        cmd = 'getMagnet'
        params = {}
        response = self._send_command(cmd, params)
        return response['result']
    
    def getLN2Level(self):
        cmd = 'getLN2Level'
        params = {}
        response = self._send_command(cmd, params)
        return response['result']

    def getLHeLevel(self):
        cmd = 'getLHeLevel'
        params = {}
        response = self._send_command(cmd, params)
        return response['result']