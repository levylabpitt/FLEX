'''
Levylab FLEX instrument driver for Quantum Design PPMS.
<https://github.com/levylabpitt/PPMS-Monitor-and-Control>

Authors: 
Pubudu Wijesinghe <pubudu.wijesinghe@levylab.org>

Contact an author for any queries.
'''

from flex.inst.base import Instrument
import time
import os

_DEFAULT_ADDRESS = 'tcp://localhost:29270'

logpath = os.path.join(os.environ.get('LOCALAPPDATA'), 'Levylab', 'FLEX', 'logs')
os.makedirs(logpath, exist_ok=True)

class PPMS(Instrument):
    def __init__(self, address=_DEFAULT_ADDRESS):
        super().__init__(address, log_file= logpath + '\instrument.log')

if __name__ == "__main__":
    # Test the PPMS class
    ppms = PPMS()
    print(ppms.help())
    ppms.close()