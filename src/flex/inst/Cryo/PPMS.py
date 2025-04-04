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
    
    def setTemperature(self, value: float, rate: float) -> None:
        cmd = 'Set Temperature'
        param = {'Temperature (K)': value, 'Rate (K/min)': rate}
        self._send_command(cmd, param)

    def getTemperature(self) -> float:
        cmd = 'Get Temperature'
        response = self._send_command(cmd)
        return response['result']

    def setMagnet(self, field: float, rate: float) -> None:
        cmd = 'Set Magnet'
        param = {'Field (T)': field, 'Rate (T/min)': rate}
        self._send_command(cmd, param)
    
    def getMagnet(self) -> float:
        cmd = 'Get Magnet'
        response = self._send_command(cmd)
        return response['result']

# -------------- Custom functions ---------------->

    def _is_temperature_set(self, target_temp):
        current_temp = self.getTemperature()['Temperature (K)']
        if current_temp is not None:
            return current_temp == target_temp
        return False

    def _is_field_set(self, target_field):
        current_field = self.getMagnet()['Field (T)']
        if current_field is not None:
            return current_field == target_field
        return False

    def setTemperatureAndWait(self, target_temp: float, rate: float, timeout: float = 600) -> None:
        self.setTemperature(target_temp, rate)
        start_time = time.time()
        while not self._is_temperature_set(target_temp):
            if time.time() - start_time > timeout:
                raise TimeoutError("Temperature setting timed out.")
            time.sleep(1)
        print(f"Temperature set to {target_temp} K.")
    
    def setMagnetAndWait(self, target_field: float, rate: float, timeout: float = 600) -> None:
        self.setMagnet(target_field, rate)
        start_time = time.time()
        while not self._is_field_set(target_field):
            if time.time() - start_time > timeout:
                raise TimeoutError("Field setting timed out.")
            time.sleep(1)
        print(f"Magnetic field set to {target_field} T.")

if __name__ == "__main__":
    # Test the PPMS class
    ppms = PPMS()
    print(ppms.help())
    ppms.close()