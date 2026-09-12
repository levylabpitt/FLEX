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
from typing import TYPE_CHECKING, Any, Union, Sequence, Optional, Callable


class Parameter:
    """A named, unit-carrying read handle on an instrument."""

    def __init__(
        self,
        name: str,
        *,
        instrument: Any = None,
        getter: Callable[[], Any] | None = None,
        setter: Callable[[Any], None] | None = None,
        unit: str = "",
        doc: str = "",
    ):
        self.name = name
        self.instrument = instrument
        self.unit = unit
        self.__doc__ = doc or f"Parameter {name}" + (f" [{unit}]" if unit else "")
        self.doc = self.__doc__
        self._getter = getter
        self._setter = setter

    @property
    def full_name(self) -> str:
        return f"{self.instrument.name}.{self.name}" if getattr(self.instrument, "name", None) else self.name

    @property
    def gettable(self) -> bool:
        return self._getter is not None

    @property
    def settable(self) -> bool:
        return self._setter is not None

    def get(self) -> Any:
        if self._getter is None:
            raise NotImplementedError(f"Parameter {self.full_name!r} is not readable")
        return self._getter()

    def set(self, value: Any) -> None:
        if self._setter is None:
            raise NotImplementedError(f"Parameter {self.full_name!r} is not writable")
        self._setter(value)

    def __call__(self, *value: Any) -> Any:
        if not value:
            return self.get()
        if len(value) == 1:
            return self.set(value[0])
        raise TypeError(f"Parameter takes 0 (get) or 1 (set) arguments, got {len(value)}")

    def __repr__(self) -> str:
        unit = f", unit={self.unit!r}" if self.unit else ""
        return f"Parameter({self.full_name!r}{unit})"


class ZMQInstrumentError(RuntimeError):
    """The instrument answered with a JSON-RPC error."""

    def __init__(self, message: str, code: Optional[int] = None, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


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
        timeout: Union[float, str] = 5,
        log_file: Optional[str] = None,
        connect_check: bool = True,
        name: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        **kwargs: Any,
    ):
        # Flexible argument resolution: handle both (address, timeout) and (name, address, timeout)
        if isinstance(timeout, str) and ("://" in timeout or "localhost" in timeout or "127.0.0.1" in timeout):
            name = str(address)
            address = str(timeout)
            actual_timeout = float(kwargs.pop("timeout", 5.0)) if isinstance(kwargs.get("timeout"), (int, float)) else 5.0
        else:
            actual_timeout = float(timeout) if isinstance(timeout, (int, float)) else 5.0

        # Initialize logging
        self.name = name or self.__class__.__name__
        self.metadata = metadata or {}
        self.parameters: dict[str, Parameter] = {}
        self.logger = logging.getLogger(f"inst.{self.name}")
        self.log = self.logger
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

        self.context = zmq.Context()
        self._address = address
        self._timeout = actual_timeout
        self._req_id = 0
        self.socket = None

        try:
            self._connect()
            if connect_check:
                self._send_command("ACK")
            self.logger.info(f"Instrument initialized with address: {address}")
        except Exception as e:
            self.close()
            self.logger.error(f"Error while initializing: {e}")
            raise

    def _connect(self) -> None:
        """Create and connect the ZMQ REQ socket."""
        if self.socket is not None:
            try:
                self.socket.close(linger=0)
            except Exception:
                pass
        self.socket = self.context.socket(zmq.REQ)
        self.socket.setsockopt(zmq.LINGER, 0)
        self._apply_timeout(self._timeout)
        self.socket.connect(self._address)

    def _apply_timeout(self, timeout: Optional[float]) -> None:
        if self.socket is None:
            return
        if timeout is None:
            self.socket.setsockopt(zmq.RCVTIMEO, -1)
            self.socket.setsockopt(zmq.SNDTIMEO, -1)
        else:
            ms = int(timeout * 1000)
            self.socket.setsockopt(zmq.RCVTIMEO, ms)
            self.socket.setsockopt(zmq.SNDTIMEO, ms)

    def idn(self) -> dict[str, Optional[str]]:
        """
        JSON request of IDN should return this information from the IF.
        """
        self.logger.debug("Fetching IDN information.")
        response = self._send_command("IDN")
        if response and "result" in response:
            return response["result"]
        return None

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
        self._timeout = timeout
        self._apply_timeout(timeout)

    def _get_zmq_timeout(self) -> Union[float, None]:
        if self.socket is None:
            return self._timeout
        timeout = self.socket.getsockopt(zmq.RCVTIMEO)
        if timeout == -1:
            return None
        else:
            return timeout / 1000.0

    def close(self) -> None:
        """Disconnect and irreversibly tear down the instrument."""
        self.logger.info(f"Closing server connection for {self._address}...")
        try:
            if getattr(self, 'socket', None) is not None:
                self.socket.close(linger=0)
                self.socket = None
            if getattr(self, 'context', None) is not None:
                self.context.term()
                self.context = None
        except Exception as e:
            self.logger.error(f"Error while closing: {e}")

    def call(self, method: str, params: Any = None, *, timeout: Optional[float] = None) -> Any:
        """Send one JSON-RPC request and return its 'result'."""
        response = self._send_command(method, params or {}, timeout=timeout)
        return response.get("result") if isinstance(response, dict) else response

    def add_parameter(
        self,
        name: str,
        getter: Optional[Callable[[], Any]] = None,
        setter: Optional[Callable[[Any], None]] = None,
        unit: str = "",
        doc: str = "",
    ) -> Parameter:
        """Register a parameter handle on this instrument."""
        param = Parameter(name, instrument=self, getter=getter, setter=setter, unit=unit, doc=doc)
        self.parameters[name] = param
        return param

    def snapshot(self, read: bool = False) -> dict[str, Any]:
        """Return a snapshot of all registered parameters."""
        snap = {
            "name": self.name,
            "address": self._address,
            "metadata": self.metadata,
            "parameters": {},
        }
        for name, param in self.parameters.items():
            if read and param.gettable:
                try:
                    snap["parameters"][name] = {"value": param.get(), "unit": param.unit}
                except Exception as e:
                    snap["parameters"][name] = {"error": str(e), "unit": param.unit}
            else:
                snap["parameters"][name] = {"unit": param.unit}
        return snap

    def _next_id(self) -> str:
        self._req_id += 1
        return str(self._req_id)

    def _send_command(self, cmd: str, params: dict = {}, timeout: Optional[float] = None, *args: Any) -> dict:
        command: dict = {
            "jsonrpc": "2.0",
            "method": cmd,
            "params": params,
            "id": self._next_id()
        }
        cmd_str: str = json.dumps(command)
        self.logger.debug(f"Sending command: {cmd_str}")
        response = self.ask_raw(cmd_str, timeout=timeout)
        if isinstance(response, dict) and "error" in response:
            err = response["error"]
            msg = err.get("message", "ZMQ Instrument error") if isinstance(err, dict) else str(err)
            code = err.get("code") if isinstance(err, dict) else None
            data = err.get("data") if isinstance(err, dict) else None
            raise ZMQInstrumentError(msg, code=code, data=data)
        return response

    def write_raw(self, cmd: str) -> None:
        """
        Low-level interface to send a command to the ZMQ socket.

        Args:
            cmd: The command to send to the instrument.
        """
        self.logger.debug(f"Writing raw command: {cmd}")
        if self.socket is None:
            self._connect()
        self.socket.send_string(cmd)

    def ask_raw(self, cmd: str, timeout: Optional[float] = None) -> dict:
        """
        Low-level interface to send a command to the ZMQ socket and receive a response.

        Args:
            cmd: The command to send to the instrument.

        Returns:
            dict: The instrument's response.
        """
        self.logger.debug(f"Asking raw command: {cmd}")
        if self.socket is None:
            self._connect()

        if timeout is not None:
            self._apply_timeout(timeout)
        try:
            self.socket.send_string(cmd)
            response = self.socket.recv_string()
            parsed: dict = json.loads(response)
            self.logger.debug(f"Received response: {parsed}")
            return parsed
        except (zmq.ZMQError, Exception) as e:
            self.logger.error(f"ZMQ error during ask_raw: {e}. Resetting socket.")
            self._connect()
            raise
        finally:
            if timeout is not None:
                self._apply_timeout(self._timeout)

    def __enter__(self):
        """Allows usage of the instrument as a context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Automatically closes the connection when exiting a 'with' block."""
        self.close()


if __name__ == "__main__":
    # Test the Instrument class
    import os
    address = "tcp://localhost:29170"
    logpath = os.path.join(os.environ.get('LOCALAPPDATA'), 'Levylab', 'FLEX', 'logs')
    os.makedirs(logpath, exist_ok=True)
    log_file= logpath + '\\dummy_instrument.log'
    inst = Instrument(address, log_file=log_file)
    print(inst._send_command("getResults"))
    inst.close()