'''
Levylab FLEX instrument driver for Krohn-Hite 7008.
<https://github.com/levylabpitt/Krohn-Hite-7008>

Authors: 
Pubudu Wijesinghe <pubudu.wijesinghe@levylab.org>

Contact an author for any queries.
'''

from flex.inst.base import Instrument
import time
import os

_DEFAULT_ADDRESS = 'tcp://localhost:29160'

logpath = os.path.join(os.environ.get('LOCALAPPDATA'), 'Levylab', 'FLEX', 'logs')
os.makedirs(logpath, exist_ok=True)

class KH7008(Instrument):
    def __init__(self, address= _DEFAULT_ADDRESS):
        super().__init__(address, log_file= logpath + '\instrument.log')
    
if __name__ == "__main__":
    # Test the KH7008 class
    kh = KH7008("tcp://localhost:29160",)
    print(kh.help())
    kh.close()