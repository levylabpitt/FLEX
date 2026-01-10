'''
Levylab FLEX instrument driver for Quantum Design Opticool.
<https://github.com/levylabpitt/PPMS-Monitor-and-Control>

Authors: 
Pubudu Wijesinghe <pubudu.wijesinghe@levylab.org>

Contact an author for any queries.
'''

from flex.inst.base import Instrument
from flex.db import FLEXDB
import time
import os

_DEFAULT_ADDRESS = 'tcp://localhost:29174'

logpath = os.path.join(os.environ.get('LOCALAPPDATA'), 'Levylab', 'FLEX', 'logs')
os.makedirs(logpath, exist_ok=True)

class Opticool(Instrument):
    def __init__(self, address=_DEFAULT_ADDRESS):
        super().__init__(address, log_file= logpath + '\\instrument.log')
    
    def setTemperature(self, value: float, rate: float) -> None:
        cmd = 'setTemperature'
        param = {'temperature': value, 'rate': rate, 'channel': 0}
        self._send_command(cmd, param)

    def getTemperature(self) -> float:
        cmd = 'getTemperature'
        response = self._send_command(cmd)
        return response['result']

    def setMagnet(self, field: float, rate: float) -> None:
        cmd = 'setMagnet'
        param = {'field': field, 'rate': rate, 'axis': 'Z', 'mode': 'Persistent'}
        self._send_command(cmd, param)
    
    def getMagnet(self) -> float:
        cmd = 'getMagnet'
        response = self._send_command(cmd)
        return response['result']
    
    def setChamber(self):
        pass

    def getChamber(self):
        cmd = 'getChamber'
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

    def get_temp_from_db(self, start_time, end_time):
        db = FLEXDB('levylab', 'llab_admin')
        sql = """
            SELECT d000 FROM llab_074
            WHERE time BETWEEN %s AND %s
        """
        params = (start_time, end_time)
        result = db.execute_fetch(sql, params, method='all')
        db.close_connection()
        return result

if __name__ == "__main__":
    # Test the PPMS class
    opticool = Opticool()
    print(opticool.help())
    # data = opticool.get_temp_from_db('2025-05-09 07:00:08.638105', '2025-05-09 07:30:00.543921')
    # print(data)
    opticool.close()