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
import numpy as np
import pandas as pd

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

    #def get_ao(self, channel):
        cmd = 'getAO'
        params = {'channel': channel}
        response = self._send_command(cmd, params)
        return response['result']
      
    
    def set_amplitude(self, channel: int, value: float) -> None:
        """
        This function will set the amplitude value of the associated output channel. 
        The channel parameter corresponds to the channel no. and the value parameter corresponds to the amplitude value.
        """
        cmd = 'setAO_Amplitude'
        param = {'AO Channel': channel, 'Amplitude (V)': value}
        self._send_command(cmd, param)
        time.sleep(0.1) # remove this when pubudu fixes the send_command function.
        a = self._get_AO_param(channel, 'Amplitude')
        print(a, value)
        if a != value:
            raise Exception('Value could not be changed. Maximum amplitude value might be limited.')
        

    def set_dc(self, channel: int, value: float) -> None:
        """
        This function will set the dc value of the associated output channel. 
        The channel parameter corresponds to the channel no. and the value parameter corresponds to the dc value.
        """
        cmd = 'setAO_DC'
        param = {'AO Channel': channel, 'DC (V)': value}
        self._send_command(cmd, param)
        time.sleep(0.1)
        a = self._get_AO_param(channel, 'DC')
        print(a, value)
        if a != value:
            raise Exception('Value could not be changed.')

    def set_freq(self, channel: int, value: float) -> None:
        """
        This function will set the frequency value of the associated output channel. 
        The channel parameter corresponds to the channel no. and the value parameter corresponds to the frequency value.
        """
        cmd = 'setAO_Frequency'
        param = {'AO Channel': channel, 'Frequency (Hz)': value}
        self._send_command(cmd, param)
        time.sleep(0.1)
        a = self._get_AO_param(channel, 'Frequency')
        if a != value:
            raise Exception('Value could not be changed. Frequency might be linked.')

    def set_phase(self, channel: int, value: float) -> None:
        """
        This function will set the phase value of the associated output channel. 
        The channel parameter corresponds to the channel no. and the value parameter corresponds to the phase value.
        """
        cmd = 'setAO_Phase'
        param = {'AO Channel': channel, 'Phase (deg)': value}
        self._send_command(cmd, param)
        time.sleep(0.1)
        a = self._get_AO_param(channel, 'Phase')
        if a != value:
            raise Exception('Value could not be changed.')

    def set_func(self, channel: int, value: str) -> None:
        """
        Set the function of the specified analog output (AO) channel.
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
        a = self._get_AO_param(channel, 'Function')
        if a != value:
            raise Exception('Value could not be changed.')
        


    def get_lockin(self, channel: int, param: str, ref: int) -> float:
        """
        This function has the general structure for making any getter function.
        """
        key = f"AI{channel}.Ref{ref}.{param}"
        response = self._send_command('getResults')
        results = response['result']['Results (Dictionary)']
        results_dict = {item['key']: item['value'] for item in results}
        return results_dict.get(key)
    
    
    def _get_AO_param(self, channel: int, param: str) -> None:
        """
        Get the parameter value of the speicified channel.
        channel (int): The AO channel number to get the parameter value for.
        param (str): Amplitude, DC, Frequency, Phase, Function
        """
        response = self._get_AO()
        data = response
        if param == 'Amplitude':
           param1 = 'Amplitude'
        elif param == 'DC':
           param1 = 'Offset'
        elif param == 'Frequency':
           param1 = 'Frequency' 
        elif param == 'Phase':
           param1 = 'Phase'  
        elif param == 'Function':
            param1 = 'Function'
        parameter_channel_no = [item[param1] for item in data['result'] if item['Channel']==channel]
        parameter_value = parameter_channel_no[0]
        return parameter_value
    
    
    def set_state(self, value: str) -> None:
        """
        This function will set the status of the MCLockin state from previous to the new one as given by value parameter.
        """
        cmd = 'setState'
        param = value
        self._send_command(cmd, param)
    
    def get_state(self) -> str:
        """
        This function will get the status of the state in which the MCLockin is currently operating at.
        """
        cmd = 'getState'
        return self._send_command(cmd)['result']
    
    def set_sweepTime(self, value: float) -> None:
        """
        This function will set the sweeptime as given by the value parameter.
        """
        cmd = 'setSweepTime'
        param = value
        self._send_command(cmd, param)
    
    #def set_sampling_mode(self, value: str) -> None:
        #cmd = 'setSamplingFsMode'
        #param = value
        #self._send_command(cmd, param)
    
    def getsweepdata(self):
        """
        This function will get the sweep AO/AI data and sweep lockin data from the MCLockin after a sweep is completed.
        """
        response = self._send_command('getSweepWaveforms')
        return response
    
    def _data_extraction(self, extract_channel=None):
        """
       This function extracts sweep data for a specified output channel. If no channel is specified (extract_channel = "None"), it extracts data for all channels. 
       The function returns an array containing sweep AI, sweep AO, sweeping results X(V), and sweeping results Y(V) for all channels. 
       These arrays are located at indices 0, 1, 2, and 3 of the output array, respectively.  
        """
        data = self.getsweepdata()
        ai_array = [entry['Y'] for entry in data['result']['AI_wfm']]
        dfai = pd.DataFrame(ai_array).transpose()
        ao_array = [entry['Y'] for entry in data['result']['AO_wfm']]
        dfao = pd.DataFrame(ao_array).transpose()
        y_array = [entry['Y'] for entry in data['result']['Y_wfm']]
        dfy = pd.DataFrame(y_array).transpose()
        x_array = [entry['Y'] for entry in data['result']['X_wfm']]
        dfx = pd.DataFrame(x_array).transpose()
        if extract_channel == None:
            print("extracted everything")
            return [np.array(dfai), np.array(dfao), np.array(dfx), np.array(dfy)]
        else:
            print('extracted the specified channel')
            return [np.array(dfai[extract_channel - 1]), np.array(dfao[extract_channel - 1]), np.array(dfx[extract_channel - 1]), np.array(dfy[extract_channel - 1])]

    def set_sweepconfig(self, channel_configs: list, initial_wait: float, sweep_time: float) -> None:
        '''
        Sets the sweep configuration for the lock-in
        to do sweep. The sweep can be done using single and multiple channels.
        Args:
           channel_configs: A list contains all the parameter values for sweeping. For a single channel sweep,
           the parameter list will have the structure- [[channel,start sweep voltage, end sweep voltage, pattern,a list[] for table pattern (only if required)]].
           For sweeping with 'n' multiple channels, the list structure will be- [[parameter list for channel 1], [parameter list for channel 2],
           .....,[ parameter list for channel n]].
        '''
        channel_configs_list = []
        for channel in channel_configs:
            channel_configs_list.append({
            "Enable?":True,
            "Channel":channel[0],
            "Start":channel[1],
            "End":channel[2],
            "Pattern": channel[3],    
            "Table": channel[4] if channel[3] == "Table" else []})
        
        param = {
        "Sweep Time (s)":sweep_time,
        "Initial Wait (s)":initial_wait,
        "Return to Start":False,
        "Channels":channel_configs_list}

        self._send_command('setsweep',param)

    def sweep_yet_starting(self) -> None:
        """
        This function checks whether the sweep process has started or not after the user commands MCLockin to sweep.
        """
        while self.get_state() == 'started':
             time.sleep(0.2) 

    def sweep_checking(self) -> None:  
        """
        This function checks whether the sweep process is completed or not.
        """
        while self.get_state() == 'sweeping':
             time.sleep(0.2)

    def sweep(self, channel_configs: list, initial_wait: float, sweep_time: float, extract: float) -> None:
        """
        This function can perfom sweep in a single channel and in mutliple channels of MClockin. This function returns a general output array containing the sweep AI, sweep AO, sweeping results X(V) & 
        sweeping results Y(V) arrays. So, the sweep AI array, the sweep AO array, the sweeping results X(V) array & the sweeping results Y(V) array
        are the 0-index, 1-index, 2-index & 3-index elements respectively of the general output array. For example, let 'x' be the output array. Then, x[0] = sweep AI data; x[1] = sweep AO data, 
        x[2] = sweeping results X data; x[3] = sweeping results Y data.

        Args:
        channel_configs: A parameter list contains all the parameter values for sweeping. For a single channel sweep,
           the parameter list will have the structure- [channel,start sweep voltage, end sweep voltage, pattern,[a list for table pattern only if required]].
           For sweeping with 'n' multiple channels, the list structure will be- [[parameter list for channel 1], [parameter list for channel 2],
           .....,[ parameter list for channel n]].
        initial_wait: wait time before sweeping starts
        sweep_time: The time of the sweep
        extract: output channel no. (To get 
        data for all channels, use default
        value "None".)

        """
        if self.get_state() == 'sweeping':
            raise Exception('Request Denied! Already sweeping')    
        elif self.get_state() == 'idle':
            self.set_state('start')  

        self.set_sweepconfig(channel_configs, initial_wait,sweep_time)
        self.set_state('start sweep')
        self.sweep_yet_starting()
        self.sweep_checking()
        print('sweep completed')
        sdata = self._data_extraction(extract)
        return sdata
         
        
    #def sweep1d(self, sweep_channel, start, stop, duration, measure_channel):
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

    def set_sampling(self, FS: float, s: float) -> None:
        """
        This function sets the sampling rate and no. of samples as given by the 'FS' and 's' parameters respectively. 
        """
        param = {'Fs': FS, '#s':s}
        self._send_command('setSampling',param)

    def get_sampling(self):
        """
        This function gets the values of Sampling rate (Fs) and number of samples (#s)
        """
        response = self._send_command('getSampling')
        return response
    
    def set_ref(self, ref_configs: list) -> None:
        """
        This function set the parameter values of reference channels for MCLockin.

        Arguments: 
        ref_configs: A parameter list contains all the parameters of a reference channel.
        For a single channel, the parameter list will have the structure- [[Channel, Frequency, Phase, TC, Roll-Off]].
        For 'n' multiple channels, the list structure will be- [[parameter list for channel 1], [parameter list for channel 2],
        .....,[ parameter list for channel n]].

        """
        ref_configs_list = []

        for ref in ref_configs:
            ref_configs_list.append({
            "Enable?": True,
            "Channel": ref[0],
            "Frequency": ref[1],
            "Phase": ref[2],
            "TC": ref[3],
            "Roll-Off": ref[4]
            })

        param = ref_configs_list
        #print(param)
        self._send_command('setREF',param)
        
        

    def get_ref(self):
        """
        This function shows the parameter values of all the reference channels
        """
        response = self._send_command('getREFconfig')
        return response
    
    def get_ref_param(self, channel: int, param: str):
        """
        Get the parameter value of the speicified channel.
        channel (int): The reference channel number to get parameter value for.
        param (str): Frequency, Phase, TC, Roll-Off
        """
        response = self.get_ref()
        data = response
        parameter_channel_no = [item[param] for item in data['result'] if item['Channel']==channel]
        parameter_value = parameter_channel_no[0]
        return parameter_value
    
    def set_REF_frequency(self, REFch: float, freq: float) -> None:
        """
        This function will set the value for frequency of a reference channel given by the parameters- REFch and freq. 
        REFch specifies the channel no. and freq specifies the frequency value.
        """
        param = {'REF Channel':REFch, 'Frequency (Hz)': freq}
        self._send_command('setREF_Frequency',param)
        time.sleep(0.1)
        a = self.get_ref_param(REFch,'Frequency')
        if a != freq:
          raise Exception('Value could not be changed. Frequency might be linked.')
        

    def set_REF_TC(self, REFch: float, TC: float) -> None:
        """
        This function will set the value for Time Constant (TC) of a reference channel by the parameters- REFch and TC.
        REFch specifies the channel no. and TC specifies the Time constant value.
        """
        param = {'REF Channel': REFch, 'TC (s)':TC}
        self._send_command('setREF_TC',param)
        time.sleep(0.1)
        a = self.get_ref_param(REFch,'TC')
        if a != TC:
          raise Exception('Value could not be changed.')

        


    


if __name__ == "__main__":
    # Test the MCLockin class
    lockin = MCLockin("tcp://localhost:29170",)
    lockin.set_amplitude(1, 3)
    # lockin.set_freq(1, 13)
    # lockin.set_func(1, 'Sine')
    # print(lockin.get_lockin(channel=1, param='Theta', ref=1))
    lockin.close()
