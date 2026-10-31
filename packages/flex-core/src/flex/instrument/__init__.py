"""The instrument model: ``Instrument``, ``Parameter`` and validators, and
``SimulatedInstrument`` (no hardware; tests and ``simulate = true``). Connection bases
are in ``flex.protocols``."""

from flex.instrument.base import Instrument
from flex.instrument.parameter import Enum, Numbers, Parameter
from flex.instrument.simulated import SimulatedInstrument

__all__ = [
    "Enum",
    "Instrument",
    "Numbers",
    "Parameter",
    "SimulatedInstrument",
]
