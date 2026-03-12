'''
Levylab FLEX instrument driver for Levylab MNK - OI1820
<https://github.com/levylabpitt/Oxford-1820>

Authors:
Pubudu Wijesinghe <pubudu.wijesinghe@levylab.org>

Contact an author for any queries.
'''

from flex.inst.base import Instrument
from flex.inst.levylab.insttypes.Magnet import Magnet
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
        return super().getMagnet()
    
    def setMagnet(self, field, rate, axis = "Z", mode = "Persistent"):
        return super().setMagnet(field, rate, axis, mode)

    def getMagnetTarget(self):
        return super().getMagnetTarget()


if __name__ == "__main__":
    mnk_mag = Oxford1820()
    print(f"Magnetic field: {mnk_mag.getMagnet()}")
    mnk_mag.close()