'''
Levylab FLEX instrument driver for Levylab Multichannel-lockin
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

_DEFAULT_ADDRESS = 'tcp://localhost:29170'

logpath = os.path.join(os.environ.get('LOCALAPPDATA'), 'Levylab', 'FLEX', 'logs')
os.makedirs(logpath, exist_ok=True)

class MCLockin(Instrument):
    def __init__(self, address=_DEFAULT_ADDRESS):
        super().__init__(address, log_file= logpath + '\instrument.log')
          
    def getAO(self, channel):
        cmd = 'getAO'
        params = {'channel': channel}
        response = self._send_command(cmd, params)
        return response['result']
    
    def setAO_Amplitude(self, channel: int, value: float) -> None:
        cmd = 'setAO_Amplitude'
        param = {'Channel': channel, 'Amplitude': value}
        self._send_command(cmd, param)

    def setAO_DC(self, channel: int, value: float) -> None:
        cmd = 'setAO_DC'
        param = {'AO Channel': channel, 'DC (V)': value}
        self._send_command(cmd, param)

    def setAO_Frequency(self, channel: int, value: float) -> None:
        cmd = 'setAO_Frequency'
        param = {'AO Channel': channel, 'Frequency (Hz)': value}
        self._send_command(cmd, param)

    def setAO_Phase(self, channel: int, value: float) -> None:
        cmd = 'setAO_Phase'
        param = {'AO Channel': channel, 'Phase (deg)': value}
        self._send_command(cmd, param)

    def setAO_Function(self, channel: int, value: str) -> None:
        """
        Set the function of the specified analog output (AO) channel.
        Parameters:
        channel (int): The AO channel number to set the function for.
        value (str): The function to set for the AO channel. Must be one of {"Sine", "Triangle", "Square"}.
        Raises:
        ValueError: If the provided value is not one of the allowed values.
        """

        allowed_values = {"Sine", "Triangle", "Square"}
        if value not in allowed_values:
            raise ValueError(f"Invalid value: {value}. Allowed values are: {', '.join(allowed_values)}")
        
        cmd = 'setAO_Function'
        param = {'AO Channel': channel, 'Function': value}
        self._send_command(cmd, param)

    def getResults(self) -> dict:
        cmd = 'getResults'
        return self._send_command(cmd)['result']
    
    def setState(self, value: str) -> None:
        cmd = 'setState'
        param = {"State": value}
        self._send_command(cmd, param)
    
    def getState(self) -> str:
        cmd = 'getState'
        return self._send_command(cmd)['result']
    
    def setSweepTime(self, value: float) -> None:
        cmd = 'setSweepTime'
        param = value
        self._send_command(cmd, param)
    
    def setSamplingMode(self, value: str) -> None:
        cmd = 'setSamplingFsMode'
        param = value
        self._send_command(cmd, param)
    
    def getSweepWaveforms(self) -> dict:
        cmd = 'getSweepWaveforms'
        return self._send_command(cmd)['result']

    def setSweep(self, channel: int, start: float, stop: float, sweep_time: float) -> None:
        '''
        Sets the sweep configuration for the lock-in
        Currently only supports one channel
        Args:
            channel: The channel to set the sweep configuration for
            start: The start time of the sweep
            stop: The stop time of the sweep
            sweep_time: The time of the sweep
            pattern: The pattern of the sweep
        '''
        param = {"Sweep Time (s)":sweep_time,
                 "Initial Wait (s)":2,
                 "Return to Start":False,
                 "Channels":[{"Enable?":True,
                              "Channel":channel,
                              "Start":start,
                              "End":stop,
                              "Pattern": "Ramp /",
                              "Table":[]}]}      
        self._send_command('setSweep', param)


# -------------- Custom functions ---------------->

    def get_lockin_result(self, channel: int, param: str, ref: int = 1) -> float:
        key = f"AI{channel}.{param}" if param == "Mean" else f"AI{channel}.Ref{ref}.{param}"
        response = self._send_command('getResults')
        results = response['result']['Results (Dictionary)']
        results_dict = {item['key']: item['value'] for item in results}
        return results_dict.get(key)

    def sweep1d(self, sweep_config: dict, plot_data=False, timeout=10) -> None:
        sweep_channel = sweep_config.get('sweep_channel')
        start = sweep_config.get('sweep_start')
        stop = sweep_config.get('sweep_stop')
        duration = sweep_config.get('duration')
        measure_channel = sweep_config.get('measure_channel')
        
        if self.getState() == 'sweeping':
            raise Exception('Request Denied! Already sweeping')    
        elif self.getState() == 'idle':
            self.setState('start')   
        # TODO: The state check should be happening with another function
        self.setSweep(sweep_channel, start, stop, duration)
        time.sleep(0.5)
        self.setState('start sweep')
        # *wait for the sweep time since it'll anyway take that long (saves processor resources)
        time.sleep(duration) 
        start_time = time.time()
        while self.getState() == 'sweeping':
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Sweep operation timed out after {timeout} seconds. Please check the Multichannel Lock-in Application.")
            time.sleep(0.5)

        
if __name__ == "__main__":
    # Test the MCLockin class
    lockin = MCLockin("tcp://localhost:29170",)
    lockin.set_amplitude(1, 0.01)
    lockin.set_freq(1, 13)
    lockin.set_func(1, 'Sine')
    print(lockin.get_lockin(channel=1, param='Theta', ref=1))
    lockin.close()
