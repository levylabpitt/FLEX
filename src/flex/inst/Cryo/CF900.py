'''
Levylab FLEX instrument driver for CF900 - OIVRM and Leiden TC (Z Bridge)
<https://github.com/levylabpitt/Oxford-VRM>
<https://github.com/levylabpitt/Leiden-FP-and-TC>

Authors:
Pubudu Wijesinghe <pubudu.wijesinghe@levylab.org>
Aria Hajikhani <aria.hajikhani@levylab.org>

Contact an author for any queries.
'''

from flex.inst.base import Instrument
import os

# Default addresses for the subsystems
_DEFAULT_ADDRESS_MAGNET = 'tcp://localhost:21213'
_DEFAULT_ADDRESS_TEMP = 'tcp://10.226.177.XXX:10025' 

# Path to the log file
logpath = os.path.join(os.environ.get('LOCALAPPDATA'), 'Levylab', 'FLEX', 'logs')
os.makedirs(logpath, exist_ok=True)


class _CFMagnet(Instrument):
    '''
    Internal: Oxford VRM Magnet subsystem.
    Not intended for direct use - use MNK class instead.
    '''
    def __init__(self, address=_DEFAULT_ADDRESS_MAGNET):
        super().__init__(address, log_file=logpath + '\\instrument.log')

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

class _CFTemp(Instrument):
    '''
    Internal: Leiden Temperature subsystem.
    Not intended for direct use - use MNK class instead.
    '''
    def __init__(self, address=_DEFAULT_ADDRESS_TEMP):
        super().__init__(address, log_file=logpath + '\\instrument.log')
    
    def getTemperature(self, channel):
        cmd = 'getTemperature'
        params = [channel]
        response = self._send_command(cmd, params)
        return response['result']
    
    def getHeater(self, channel):
        cmd = 'getHeater'
        params = [channel]
        response = self._send_command(cmd, params)
        return response['result']


class CF900:
    '''
    Leiden CF900 - unified interface for magnet and temperature control.
    
    This super instrument consists of two subsystems with different network addresses:
    - Magnet controller (Oxford VRM)
    - Temperature controller (Leiden TC (Z Bridge))
    '''
    
    def __init__(self, 
                 magnet_address=_DEFAULT_ADDRESS_MAGNET,
                 temp_address=_DEFAULT_ADDRESS_TEMP):
        '''
        Initialize MNK instrument with both subsystems.
        
        Args:
            magnet_address: ZMQ address for magnet controller
            temp_address: ZMQ address for temperature controller
        '''
        self._magnet = _CFMagnet(magnet_address)
        self._temp = _CFTemp(temp_address)

    def getMagnet(self):
        '''Get current magnetic field value.'''
        return self._magnet.getMagnet()
    
    def getLN2Level(self):
        return self._magnet.getLN2Level()
    
    def getTemperature(self, channel):
        '''
        Get temperature reading from specified channel.
        
        Args:
            channel: Temperature sensor channel number
        '''
        return self._temp.getTemperature(channel)
    
    def getHeater(self, channel):
        '''
        Get heater power from specified channel.
        
        Args:
            channel: Heater channel number
        '''
        return self._temp.getHeater(channel)

    def close(self):
        '''Close connections to both subsystems.'''
        self._magnet.close()
        self._temp.close()


if __name__ == "__main__":
    # Test the Oxford MNK Instrument Class
    mnk = CF900()
    print(f"Magnetic field: {mnk.getMagnet()}")
    # print(f"LN2Level: {mnk.getLN2Level()}")
    print(f"Temperature (ch 0): {mnk.getTemperature(channel=0)}")
    print(f"Heater (ch 0): {mnk.getHeater(channel=0)}")
    mnk.close()