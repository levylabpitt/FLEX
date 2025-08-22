import pyvisa
import time

class ColbyPDL:
    def __init__(self, visa_address: str, timeout: int = 5000):
        self.visa_address = visa_address
        self.rm = pyvisa.ResourceManager()  # Initialize VISA resource manager
        self.instrument = self.rm.open_resource(self.visa_address)  # Open the resource
        self.instrument.timeout = timeout  # Set the timeout for response

        self._stepper_rate = self.send_command('RATE?')

    def send_command(self, command: str):
        self.instrument.write(command)
        return self.instrument.read()
    
    def write(self, command: str):
        self.instrument.write(command)
    
    def set_delay(self, delay: float, unit: str='ns', stepper_rate: float=None):
        rate = self._stepper_rate if stepper_rate is None else stepper_rate
        self._stepper_rate = rate
        self.write(f'RATE {rate}')
        time.sleep(1)
        self.write(f'DEL {delay} {unit}')

    def get_delay(self):
        command = f'DEL?'
        response = self.send_command(command)
        return response

    def close(self):
        self.instrument.close()

# test
if __name__ == "__main__":
    import time
    visa_address = 'GPIB1::15::INSTR'
    pdl = ColbyPDL(visa_address)
    
    print(pdl.send_command('*IDN?'))
    
    pdl.set_delay(20,stepper_rate=550)
    print(pdl.get_delay())

    pdl.close()
