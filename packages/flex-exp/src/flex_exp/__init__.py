"""FLEX experiment handling.

:class:`Experiment` is the default handler; lab-specific sessions (e.g. the
LevyLab :class:`CESession`) live under :mod:`flex_exp.sessions` and are
activated through the ecosystem configuration.
"""

from flex_exp.experiment import Experiment
from flex_exp.measurement import Measurement
from flex_exp.sweep import Scan, SweepAxis, sweep

__version__ = "2.0.0a1"

__all__ = ["CESession", "Experiment", "Measurement", "Scan", "SweepAxis", "sweep"]


def __getattr__(name: str):
    if name == "CESession":
        from flex_exp.sessions.ce import CESession

        return CESession
    raise AttributeError(f"module 'flex_exp' has no attribute '{name}'")
