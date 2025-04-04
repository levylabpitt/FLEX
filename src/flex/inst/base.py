'''
WARNING: DO NOT MODIFY THIS FILE DIRECTLY.

This is the Levylab FLEX base instrument class for ZMQ communication.
The base class provides the necessary methods for communication with the Levylab Instrument Framework.
All instruments should inherit from this class and implement their own methods.

Contact Pubudu Wijesinghe <pubudu.wijesinghe@levylab.org> for any queries.
'''

import time
import json
import logging
import warnings
import zmq
from importlib.resources import as_file, files
from typing import TYPE_CHECKING, Any, Union, Sequence, Optional


class Instrument:
    """
    Base class for all instruments using ZMQ communication.
    Used for communication with Levylab Instrument Framework.

    Args:
        address: The ZMQ resource name to use to connect.
        timeout: Seconds to allow for responses. Default 5.
        metadata: Additional static metadata to add to this
            instrument's JSON snapshot.
    """

    def __init__(
        self,
        address: str,
        timeout: float = 5,
        log_file: Optional[str] = None,
        **kwargs: Any,
    ):
        # Initialize logging
        self.logger = logging.getLogger(self.__class__.__name__)
        if log_file:
            handler = logging.FileHandler(log_file)
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.DEBUG)
        else:
            logging.basicConfig(level=logging.INFO)
        try:
            self.context = zmq.Context()
            self.socket = self.context.socket(zmq.REQ)
            self.socket.connect(address)

            self._address = address
            self._timeout = timeout
            self.socket.setsockopt(zmq.RCVTIMEO, int(timeout * 1000))
            self.socket.setsockopt(zmq.SNDTIMEO, int(timeout * 1000))
            self._send_command("ACK")['result']
            self.logger.info(f"Instrument initialized with address: {address}")
        except Exception as e:
            if getattr(self, 'socket', None):
                self.socket.close()
            self.logger.error(f"Error while initializing: {e}")
            raise

    def get_idn(self) -> dict[str, Optional[str]]:
        """
        JSON request of IDN should return this information from the IF.
        """
        self.logger.debug("Fetching IDN information.")
        return {
            "vendor": "Quantum Design PPMS",
            "model": "Simulation",
            "serial": None,
            "firmware": None,
        }

    def help(self, command: str = None) -> Sequence[str]:
        self.logger.debug(f"Fetching help for method: {command}")
        if command:
            response = self._send_command("HELP", {"command": command})
            if response and "result" in response:
                return response["result"]
            return None
        else:
            response = self._send_command("HELP")
            if response and "result" in response:
                return response["result"][5:]# Skip the first 4 commands
            return None

    def _set_zmq_timeout(self, timeout: Union[float, None]) -> None:
        self.logger.debug(f"Setting ZMQ timeout to {timeout}.")
        if timeout is None:
            self.socket.setsockopt(zmq.RCVTIMEO, -1)
            self.socket.setsockopt(zmq.SNDTIMEO, -1)
        else:
            self.socket.setsockopt(zmq.RCVTIMEO, int(timeout * 1000))
            self.socket.setsockopt(zmq.SNDTIMEO, int(timeout * 1000))
        self._timeout = timeout

    def _get_zmq_timeout(self) -> Union[float, None]:
        timeout = self.socket.getsockopt(zmq.RCVTIMEO)
        if timeout == -1:
            return None
        else:
            return timeout / 1000.0

    def close(self) -> None:
        """Disconnect and irreversibly tear down the instrument."""
        self.logger.info(f"Closing server connection for {self._address}...")
        try:
            if getattr(self, 'socket', None):
                self.socket.close()
                self.context.term()
        except Exception as e:
            self.logger.error(f"Error while closing: {e}")
    
    def _send_command(self, cmd: str, params: dict = {}, *args: Any) -> str:
        command: dict = {
            "jsonrpc": "2.0", 
            "method": cmd,
            "params": params,
            "id": str(int(time.time()))
        } 
        cmd: str = json.dumps(command)
        self.logger.debug(f"Sending command: {cmd}")
        response = self.ask_raw(cmd)
        return response

    def write_raw(self, cmd: str) -> None:
        """
        Low-level interface to send a command to the ZMQ socket.

        Args:
            cmd: The command to send to the instrument.
        """
        self.logger.debug(f"Writing raw command: {cmd}")
        self.socket.send_string(cmd)

    def ask_raw(self, cmd: str) -> str:
        """
        Low-level interface to send a command to the ZMQ socket and receive a response.

        Args:
            cmd: The command to send to the instrument.

        Returns:
            str: The instrument's response.
        """
        self.logger.debug(f"Asking raw command: {cmd}")
        self.socket.send_string(cmd)
        response = self.socket.recv_string()
        time.sleep(0.1)
        response: dict = json.loads(response)
        self.logger.debug(f"Received response: {response}")
        return response

if __name__ == "__main__":
    # Test the Instrument class
    import os
    address = "tcp://localhost:29170"
    logpath = os.path.join(os.environ.get('LOCALAPPDATA'), 'Levylab', 'FLEX', 'logs')
    os.makedirs(logpath, exist_ok=True)
    log_file= logpath + '\instrument.log'
    inst = Instrument(address, log_file=log_file)
    print(inst._send_command("getResults"))
    inst.close()