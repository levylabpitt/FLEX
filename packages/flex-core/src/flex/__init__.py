"""FLEX: Framework for Laboratory EXperiments.

Re-exports the user-facing API, imported on first use.
"""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # mirror of _LAZY for editors and type checkers
    from flex.client import RemoteStation as RemoteStation
    from flex.client import connect as connect
    from flex.config import FlexConfig as FlexConfig
    from flex.config import load_config as load_config
    from flex.events import EventBus as EventBus
    from flex.instrument import Instrument as Instrument
    from flex.instrument import Parameter as Parameter
    from flex.instrument import SimulatedInstrument as SimulatedInstrument
    from flex.log import get_logger as get_logger
    from flex.protocols import SerialInstrument as SerialInstrument
    from flex.protocols import TCPInstrument as TCPInstrument
    from flex.protocols import VISAInstrument as VISAInstrument
    from flex.protocols import ZMQInstrument as ZMQInstrument
    from flex.station import Station as Station
    from flex_exp import CESession as CESession
    from flex_exp import Experiment as Experiment
    from flex_exp import Measurement as Measurement
    from flex_exp import Scan as Scan
    from flex_exp import sweep as sweep

__version__ = "2.0.0a1"

__all__ = [
    "CESession", "EventBus", "Experiment", "FlexConfig", "Instrument",
    "Measurement", "Parameter", "RemoteStation", "Scan", "SerialInstrument",
    "SimulatedInstrument", "Station", "TCPInstrument", "VISAInstrument",
    "ZMQInstrument", "connect", "get_logger", "load_config", "sweep",
]

_LAZY = {
    # flex-core
    "get_logger": "flex.log",
    "EventBus": "flex.events",
    "FlexConfig": "flex.config",
    "load_config": "flex.config",
    "Instrument": "flex.instrument",
    "Parameter": "flex.instrument",
    "SimulatedInstrument": "flex.instrument",
    "Station": "flex.station",
    "connect": "flex.client",
    "RemoteStation": "flex.client",
    "VISAInstrument": "flex.protocols",
    "TCPInstrument": "flex.protocols",
    "SerialInstrument": "flex.protocols",
    "ZMQInstrument": "flex.protocols",
    # flex-exp
    "Experiment": "flex_exp",
    "Measurement": "flex_exp",
    "Scan": "flex_exp",
    "sweep": "flex_exp",
    "CESession": "flex_exp",
}

def __getattr__(name: str):
    if name not in _LAZY:
        raise AttributeError(f"module 'flex' has no attribute '{name}'")
    module = _LAZY[name]
    try:
        return getattr(import_module(module), name)
    except ImportError as e:
        if module == "flex_exp":
            raise ImportError(f"flex.{name} needs the flex-exp package") from e
        raise


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY))
