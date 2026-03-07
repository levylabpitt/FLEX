'''
Levylab FLEX instrument driver for Levylab MNK - OI1820
<https://github.com/levylabpitt/Oxford-1820>

Authors:
Pubudu Wijesinghe <pubudu.wijesinghe@levylab.org>

Contact an author for any queries.
'''

from flex.inst.base import Instrument
from flex.inst.levylab.types.Magnet import Magnet
import os

# Default addresses for the subsystems
_DEFAULT_ADDRESS_MAGNET = 'tcp://localhost:21212'
_LABVIEW_CLASS_NAME = "Instrument.Oxford1820.lvclass"

# Path to the log file
logpath = os.path.join(os.environ.get('LOCALAPPDATA'), 'Levylab', 'FLEX', 'logs')
os.makedirs(logpath, exist_ok=True)


class Oxford1820(Instrument, Magnet):
    '''
    Internal: Oxford 1820 Magnet subsystem.
    '''
    def __init__(self, address=_DEFAULT_ADDRESS_MAGNET):
        super().__init__(address, log_file=os.path.join(logpath, "Oxford1820.log"))

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


if __name__ == "__main__":
    # Test the Oxford MNK Instrument Class
    mnk = Oxford1820()
    print(f"Magnetic field: {mnk.getMagnet()}")
    # print(f"LN2Level: {mnk.getLN2Level()}")
    print(f"Temperature (ch 0): {mnk.getTemperature(channel=0)}")
    print(f"Heater (ch 0): {mnk.getHeater(channel=0)}")
    mnk.close()