'''
Levylab FLEX instrument driver for Levylab Transport Server.
<https://github.com/levylabpitt/Transport>

Authors: 
Pubudu Wijesinghe <pubudu.wijesinghe@levylab.org>

Contact an author for any queries.
'''

from flex.inst.base import Instrument
import time
import os
from datetime import datetime, timedelta
from flex.db import db_dataviewer as dv
from typing import Literal, Union

_DEFAULT_ADDRESS = 'tcp://localhost:15260'

logpath = os.path.join(os.environ.get('LOCALAPPDATA'), 'Levylab', 'FLEX', 'logs')
os.makedirs(logpath, exist_ok=True)

class Transport(Instrument):
    def __init__(self, address=_DEFAULT_ADDRESS):
        super().__init__(address, log_file=os.path.join(logpath, "TransportServer.log"))
          
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
    
    def getStatus(self):
        cmd = 'getStatus'
        params = {}
        response = self._send_command(cmd, params)
        return response['result']['Status']
    
    def setExptFolder(self, folder: str) -> None:
        cmd = 'setExptFolder'
        param = {'folder': folder}
        self._send_command(cmd, param)

    def getExptFolder(self):
        cmd = 'getExptFolder'
        params = {}
        response = self._send_command(cmd, params)
        return response['result']['folder']

    def setExptComments(self, comments: str) -> None:
        cmd = 'setExptComments'
        param = {'comments': comments}
        self._send_command(cmd, param)

    def getExptComments(self):
        cmd = 'getExptComments'
        params = {}
        response = self._send_command(cmd, params)
        return response['result']['comments']
    
    def setExptParam(self, param: str, value: Union[str, int, float, list[str], list[int], list[float]]) -> None:

        allowed_scalar_types = (str, int, float)
        allowed_array_types = (list,)

        if isinstance(value, allowed_scalar_types):
            pass
        elif isinstance(value, allowed_array_types):
            if not value:
                pass
            elif all(isinstance(v, str) for v in value):
                pass
            elif all(isinstance(v, int) for v in value):
                pass
            elif all(isinstance(v, float) for v in value):
                pass
            else:
                raise TypeError(f"List for '{param}' must contain only str, int, or float.")
        else:
            raise TypeError(f"Value for '{param}' must be str, int, float, or list thereof.")

        cmd = "setExptParam"
        params = {param: value}
        self._send_command(cmd, params)

    # --- deprecated ---
    # def setSweepConfig(self, sweep_config: dict) -> None:
    #     sweep_channel = sweep_config.get('sweep_channel')
    #     start = sweep_config.get('sweep_start')
    #     stop = sweep_config.get('sweep_stop')
    #     duration = sweep_config.get('duration')
    #     measure_channel = sweep_config.get('measure_channel')
    #     pattern = sweep_config.get('pattern')

    #     cmd = 'setSweepConfig'
    #     param = {'sweepTime': duration,
    #             'initialWaitTime': 1,
    #             'returnToStart': False,
    #             'sweepChannels': [{'Enable?': True,
    #                                 'Channel': sweep_channel,
    #                                 'Start': start,
    #                                 'End': stop,
    #                                 'Pattern': pattern,
    #                                 'Table': [1]}
    #                                 # add more channels here if needed
    #                                 ]}
    #     self._send_command(cmd, param)

    def setSweepConfig(self, sweep_config: dict) -> None:
        cmd = 'setSweepConfig'
        param = sweep_config
        self._send_command(cmd, param)

    def getSweepConfig(self):
        cmd = 'getSweepConfig'
        params = {}
        response = self._send_command(cmd, params)
        return response['result']

# -------------- Custom functions ---------------->

    def LockinSweep(self, expt_folder:str, expt_comments:str, sweep_config: dict, run_continuous = False) -> dict:
        """
        Perform a lock-in sweep with the specified configuration.
        """
        self.setSweepConfig(sweep_config)
        self.setExptFolder(expt_folder)
        self.setExptComments(expt_comments)

        self.startTransport('LockinSweep')
        time.sleep(2)  # Allow some time for the transport to start
        if run_continuous:
            print('Continuous Sweep Running Asynchronously...')
            return None
        else:
            self.stopTransport()
            while self.getStatus() != 'idle':
                time.sleep(1)
            print('Sweep Ended.')

    def getExptDetails(self, show=False):
        folder = self.getExptFolder()
        comments = self.getExptComments()
        return folder, comments
    
if __name__ == "__main__":
    # Test the Transport Server
    transport = Transport()
    print(transport.help())
    # transport.startTransport('LockinSweep')
    # time.sleep(10)
    # transport.stopTransport()
    # transport.close()
