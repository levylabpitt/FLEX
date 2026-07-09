"""Aerotech stage / delay-line driver (placeholder).

Port of FLEX v1 ``flex.inst.levylab.Aerotech``, which was an empty stub:
its ``__init__`` never connected (the v1 default address was the literal
``tcp://localhost:XXXXX``) and every call raised ``NotImplementedError``.
The LabVIEW class name is kept so registry lookups resolve, but
constructing the driver raises until the IF app exists.
"""

from __future__ import annotations

from flex_protocols import ZMQInstrument


class Aerotech(ZMQInstrument):
    """Aerotech stage driver with DelayLine capabilities (not yet available)."""

    lv_class = "Instrument.Aerotech.lvclass"

    def __init__(self, name: str = "aerotech", address: str = "", **kwargs):
        raise NotImplementedError("Driver not available.")
