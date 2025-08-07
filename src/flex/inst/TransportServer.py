'''
Levylab FLEX instrument driver for Levylab Transport Server.
<https://github.com/levylabpitt/Multichannel-Lockin>

Authors: 
Pubudu Wijesinghe <pubudu.wijesinghe@levylab.org>

Contact an author for any queries.
'''

from flex.inst.base import Instrument
import time
import os
from datetime import datetime, timedelta
from flex.db import db_dataviewer as dv
from typing import Literal

_DEFAULT_ADDRESS = 'tcp://localhost:15260'

logpath = os.path.join(os.environ.get('LOCALAPPDATA'), 'Levylab', 'FLEX', 'logs')
os.makedirs(logpath, exist_ok=True)

class Transport(Instrument):
    def __init__(self, address=_DEFAULT_ADDRESS):
        super().__init__(address, log_file= logpath + '\instrument.log')
          
    def startTransport(self, VI: Literal['LockinTime', 'LockinSweep', 'LockinTimeDelay']) -> dict:

        allowed_values = {"LockinSweep", "LockinTime", "LockinTimeDelay"}
        if VI not in allowed_values:
            raise ValueError(f"Invalid value: {VI}. Allowed values are: {', '.join(allowed_values)}")
        cmd = 'startTransport'
        params = {'method': VI}
        response = self._send_command(cmd, params)
        return response

    def stopTransport(self):
        cmd = 'stopTransport'
        params = {}
        response = self._send_command(cmd, params)
        return response

if __name__ == "__main__":
    # Test the Transport Server
    transport = Transport()
    print(transport.help())
    transport.startTransport('LockinSweep')
    time.sleep(10)
    transport.stopTransport()
    transport.close()
