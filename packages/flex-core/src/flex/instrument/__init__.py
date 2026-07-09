"""FLEX instrument model.

:class:`Instrument` is the protocol-independent base for every driver.
Protocol base classes (``VISAInstrument``, ``ZMQInstrument``, ...) live in
the ``flex-protocols`` package; :class:`SimulatedInstrument` (here) needs no
hardware and powers tests, docs, and dry runs.
"""

from flex.instrument import capabilities
from flex.instrument.base import Instrument
from flex.instrument.parameter import Enum, Numbers, Parameter
from flex.instrument.simulated import SimulatedInstrument

__all__ = [
    "Enum",
    "Instrument",
    "Numbers",
    "Parameter",
    "SimulatedInstrument",
    "capabilities",
]
