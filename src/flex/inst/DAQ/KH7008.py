'''
Levylab FLEX instrument driver for Krohn-Hite 7008.
<https://github.com/levylabpitt/Krohn-Hite-7008>

Authors: 
Pubudu Wijesinghe <pubudu.wijesinghe@levylab.org>
Aria Hajikhani <aria.hajikhani@levylab.org>

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
    
    def set_all_channels(self, channels_config):
        cmd = 'setAllChannels'
        params = {'params': channels_config}
        response = self._send_command(cmd, params)
        return response.get('result')
    
    def get_all_channels(self):
        cmd = 'getAllChannels'
        response = self._send_command(cmd)
        return response.get('result')
    
    def set_channel(self, channel_config):
        cmd = 'setChannel'
        params = {'params': channel_config}
        response = self._send_command(cmd, params)
        return response.get('result')
    
    def get_channel(self, channel):
        cmd = 'getChannel'
        params = {'channel': channel}
        response = self._send_command(cmd, params)
        return response.get('result')
    
if __name__ == "__main__":
    # Test the KH7008 class
    kh = KH7008("tcp://localhost:29160",)
    print(kh.help())
    kh.close()