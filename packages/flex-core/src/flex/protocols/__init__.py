"""FLEX protocol instrument base classes.

Writing a driver is one inheritance from the class matching how the
instrument is connected::

    from flex.protocols import VISAInstrument

    class Keithley2400(VISAInstrument):
        def __init__(self, name="k2400", resource="GPIB0::24::INSTR"):
            super().__init__(name, resource)
            self.voltage = self.add_parameter(
                "voltage", get_cmd="SOUR:VOLT?", set_cmd="SOUR:VOLT {}",
                get_parser=float, unit="V",
            )

pyvisa and pyserial are optional extras, imported on first use.
"""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flex.protocols.serial import SerialInstrument as SerialInstrument
    from flex.protocols.tcp import TCPInstrument as TCPInstrument
    from flex.protocols.visa import VISAInstrument as VISAInstrument
    from flex.protocols.zmq import ZMQInstrument as ZMQInstrument
    from flex.protocols.zmq import ZMQInstrumentError as ZMQInstrumentError

__all__ = [
    "SerialInstrument", "TCPInstrument", "VISAInstrument",
    "ZMQInstrument", "ZMQInstrumentError",
]

_LAZY = {  # name -> (module, flex-core extra providing its dependency)
    "VISAInstrument": ("flex.protocols.visa", "visa"),
    "TCPInstrument": ("flex.protocols.tcp", None),
    "SerialInstrument": ("flex.protocols.serial", "serial"),
    "ZMQInstrument": ("flex.protocols.zmq", None),
    "ZMQInstrumentError": ("flex.protocols.zmq", None),
}


def __getattr__(name: str):
    if name not in _LAZY:
        raise AttributeError(f"module 'flex.protocols' has no attribute '{name}'")
    module, extra = _LAZY[name]
    try:
        return getattr(import_module(module), name)
    except ImportError as e:
        if extra and not (e.name or "").startswith("flex"):
            raise ImportError(f"{name} needs the [{extra}] extra: pip install flex-core[{extra}]") from e
        raise


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY))
