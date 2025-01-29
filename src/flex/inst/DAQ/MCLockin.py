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

_DEFAULT_ADDRESS = 'tcp://localhost:29170'

logpath = os.path.join(os.environ.get('LOCALAPPDATA'), 'Levylab', 'FLEX', 'logs')
os.makedirs(logpath, exist_ok=True)

class MCLockin(Instrument):
    def __init__(self, address=_DEFAULT_ADDRESS):
        super().__init__(address, log_file= logpath + '\instrument.log')
    
    def _get_AO(self) -> dict:
        """
        This function will get the current parameter configuration of the output channels.
        """
        response = self._send_command('getAOconfig')
        return response

    def get_ao(self, channel):
        cmd = 'getAO'
        params = {'channel': channel}
        response = self._send_command(cmd, params)
        return response['result']
    
    def set_amplitude(self, channel: int, value: float) -> None:
        cmd = 'setAO_Amplitude'
        param = {'AO Channel': channel, 'Amplitude (V)': value}
        self._send_command(cmd, param)
        a = self._get_AO_param('Amplitude (V)',channel)
        if a != value:
            raise Exception('Value could not be changed')
        

    def set_dc(self, channel: int, value: float) -> None:
        cmd = 'setAO_DC'
        param = {'AO Channel': channel, 'DC (V)': value}
        self._send_command(cmd, param)
        a = self._get_AO_param(channel, 'DC (V)')
        if a != value:
            raise Exception('Value could not be changed')

    def set_freq(self, channel: int, value: float) -> None:
        cmd = 'setAO_Frequency'
        param = {'AO Channel': channel, 'Frequency (Hz)': value}
        self._send_command(cmd, param)

    def set_phase(self, channel: int, value: float) -> None:
        cmd = 'setAO_Phase'
        param = {'AO Channel': channel, 'Phase (deg)': value}
        self._send_command(cmd, param)

    def set_func(self, channel: int, value: str) -> None:
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

    def get_lockin(self, channel: int, param: str, ref: int) -> float:
        key = f"AI{channel}.Ref{ref}.{param}"
        response = self._send_command('getResults')
        results = response['result']['Results (Dictionary)']
        results_dict = {item['key']: item['value'] for item in results}
        return results_dict.get(key)
    
    
    def _get_AO_param(self, channel: int, param: str) -> None:
        """
        Get the parameter value of the speicified channel.
        channel (int): The AO channel number to get the function for.
        param (str): 
        """
        response = self._get_AO()
        data = response
        if param == 'Amplitude (V)':
           param1 = 'Amplitude'
        if param == 'DC (V)':
           param1 = 'Offset'
        if param == 'Frequency (Hz)':
           param1 = 'Frequency' 
        if param == 'Phase (deg)':
           param1 = 'Phase'  
        parameter_channel_no = next(item[param1] for item in data['result'] if item['Channel']==channel)
        return parameter_channel_no
    
    
    def set_state(self, value: str) -> None:
        cmd = 'setState'
        param = value
        self._send_command(cmd, param)
    
    def get_state(self) -> str:
        cmd = 'getState'
        return self._send_command(cmd)['result']
    
    def set_sweepTime(self, value: float) -> None:
        cmd = 'setSweepTime'
        param = value
        self._send_command(cmd, param)
    
    def set_sampling_mode(self, value: str) -> None:
        cmd = 'setSamplingFsMode'
        param = value
        self._send_command(cmd, param)
    
    def getsweep(self):
        response = self._send_command('getSweepWaveforms')
        return response['result']

    def set_sweepconfig(self, channel: int, start: float, stop: float, sweep_time: float) -> None:
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
                 "Initial Wait (s)":1,
                 "Return to Start":False,
                 "Channels":[{"Enable?":True,
                              "Channel":channel,
                              "Start":start,
                              "End":stop,
                              "Pattern": "Ramp /",
                              "Table":[]}]}      
        self._send_command('setSweep', param)



    def sweep1d(self, sweep_channel, start, stop, duration, measure_channel):
        if self.state() == 'sweeping':
            raise Exception('Request Denied! Already sweeping')    
        elif self.state() == 'idle':
            self.state('start')   
        # TODO: The state check should be happening with another function
        self._set_sweepconfig(sweep_channel, start, stop, duration)
        time.sleep(1)
        self.state('start sweep')
        # *wait for the sweep time since it'll anyway take that long (saves processor resources)
        time.sleep(duration) 

        while self.state() == 'sweeping':
            time.sleep(0.5)
        # should have some check here to see if the sweep is done and error handling
        x = self.getsweep()['AO_wfm'][sweep_channel - 1]['Y']
        y = self.getsweep()['X_wfm'][measure_channel - 1]['Y']
        return x, y

if __name__ == "__main__":
    # Test the MCLockin class
    lockin = MCLockin("tcp://localhost:29170",)
    lockin.set_amplitude(1, 0.01)
    lockin.set_freq(1, 13)
    lockin.set_func(1, 'Sine')
    print(lockin.get_lockin(channel=1, param='Theta', ref=1))
    lockin.close()
