"""FLEX experiment handling.

:class:`Experiment` is the default handler; lab-specific sessions (e.g. the
LevyLab :class:`CESession`) live under :mod:`flex_exp.sessions` and are
activated through the FLEX configuration.
"""

from typing import TYPE_CHECKING

from flex_exp.experiment import Experiment
from flex_exp.measurement import Measurement
from flex_exp.sweep import Scan, SweepAxis, sweep

if TYPE_CHECKING:
    from flex_exp.sessions.ce import CESession as CESession

__version__ = "3.0.0a1"

__all__ = ["CESession", "Experiment", "Measurement", "Scan", "SweepAxis", "sweep"]


def __getattr__(name: str):
    if name == "CESession":
        from flex_exp.sessions.ce import CESession

        return CESession
    raise AttributeError(f"module 'flex_exp' has no attribute '{name}'")
