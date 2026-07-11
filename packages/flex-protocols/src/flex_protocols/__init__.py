"""FLEX protocol instrument base classes.

Writing a driver is one inheritance from the class matching how the
instrument is connected::

    from flex_protocols import VISAInstrument

    class Keithley2400(VISAInstrument):
        def __init__(self, name="k2400", resource="GPIB0::24::INSTR"):
            super().__init__(name, resource)
            self.voltage = self.add_parameter(
                "voltage", get_cmd="SOUR:VOLT?", set_cmd="SOUR:VOLT {}",
                get_parser=float, unit="V",
            )

Protocol dependencies (pyvisa, pyzmq, pyserial) are imported lazily so only
the protocols you use need to be installed.
"""

from importlib import import_module

__version__ = "2.0.0a1"

_LAZY = {
    "VISAInstrument": ("flex_protocols.visa", "pyvisa", "visa"),
    "TCPInstrument": ("flex_protocols.tcp", None, None),
    "SerialInstrument": ("flex_protocols.serial", "pyserial", "serial"),
    "ZMQInstrument": ("flex_protocols.zmq", "pyzmq", "zmq"),
    "ZMQInstrumentError": ("flex_protocols.zmq", "pyzmq", "zmq"),
}


def __getattr__(name: str):
    if name in _LAZY:
        module, dependency, extra = _LAZY[name]
        try:
            return getattr(import_module(module), name)
        except ImportError as e:
            if dependency and e.name in (dependency, extra):
                raise ImportError(
                    f"{name} requires {dependency}. Install it with: "
                    f"pip install flex-protocols[{extra}]"
                ) from e
            raise
    raise AttributeError(f"module 'flex_protocols' has no attribute '{name}'")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY))
