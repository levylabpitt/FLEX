import zmq
import json
import time
import logging
import os

class Instrument:
    def __init__(self, name, host='localhost', port=29170, log_file='instrument.log'):
        self.name = name
        self.host = host
        self.port = port
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.connect(f'tcp://{self.host}:{self.port}')
        
        # Log to file and console
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        
        self._initialize_commands()
        self._generate_stub()

    def _send_command(self, command):
        try:
            message = json.dumps(command)
            self.socket.send_string(message)
            response = self.socket.recv_string()
            return json.loads(response)
        except (zmq.ZMQError, json.JSONDecodeError) as e:
            self.logger.error(f"Error sending command: {e}")
            return None
    
    def help(self, method=None):
        if method:  
            command = {
                "jsonrpc": "2.0", 
                "method": "HELP", 
                "params": {"Command": method},
                "id": "9999"
            }
        else:
            command = {
                "jsonrpc": "2.0", 
                "method": "HELP", 
                "id": "9998"
            }
        response = self._send_command(command)
        if response and "result" in response:
            return response["result"]
        return None
    
    def _initialize_commands(self):
        self._commands = self.help() or []  # Store available commands
        for command in self._commands:
            self._create_command_method(command)
    
    def _create_command_method(self, command_name):
        def method(self, **kwargs):
            command = {
                "jsonrpc": "2.0", 
                "method": command_name, 
                "params": kwargs,
                "id": str(int(time.time()))
            }
            print(command)
            response = self._send_command(command)
            if response and "result" in response:
                return response["result"]
            return None
        
        setattr(self, command_name, method.__get__(self))
        self.logger.info(f"Created method '{command_name}' for instrument '{self.name}'")
    
    def _generate_stub(self):
        """Dynamically creates a .pyi stub file for VS Code autocompletion."""
        stub_path = os.path.join(os.path.dirname(__file__), "Instrument.pyi")
        with open(stub_path, "w") as f:
            f.write(f"class Instrument:\n")
            f.write(f"    def __init__(self, name: str, host: str = 'localhost', port: int = 29170, log_file: str = 'instrument.log'): ...\n\n")
            for cmd in self._commands:
                f.write(f"    def {cmd}(self, **kwargs) -> None: ...\n")
        print(f"Stub file generated: {stub_path}")


if __name__ == "__main__":
    print('running {}...'.format(__file__))
    # log_file = 'instcomm_v3.log'
    # lockin = Instrument(name='lockin', port=29170, log_file=log_file)
    # ppms = Instrument(name='ppms', port=29270, log_file=log_file)
    # print(lockin.help('Set Temperature'))
    # lockin.getAUX()
    # print(*lockin.help(), sep='\n') # better if we can give some documentation here
