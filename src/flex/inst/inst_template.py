'''
Levylab FLEX instrument driver for 'Dummy Instrument'.
<Github link for the Instrument Framework Software>

Authors: 
Your Name <Your email>

Contact an author for any queries.
'''

from flex.inst.base import Instrument
import os

# Default address for the instrument (https://github.com/levylabpitt/Instrument-Framework/wiki/Port-Numbers)
_DEFAULT_ADDRESS = 'tcp://localhost:29160' 

# Path to the log file
logpath = os.path.join(os.environ.get('LOCALAPPDATA'), 'Levylab', 'FLEX', 'logs')
os.makedirs(logpath, exist_ok=True)

class Dummy(Instrument):
    '''
    Documentation for the Dummy Instrument class.
    '''
    def __init__(self, address= _DEFAULT_ADDRESS):
        super().__init__(address, log_file= logpath + '\instrument.log')
    
    # Define the instrument-specific methods here
    def test_method(self, channel):
        '''
        Documentation for the test_method.'''
        cmd = 'getAO'
        params = {'channel': channel}
        response = self._send_command(cmd, params)
        return response['result']

if __name__ == "__main__":
    # Test the Dummy Instrument class
    dummy_inst = Dummy("tcp://localhost:29160",)
    print(dummy_inst.help())
    dummy_inst.close()