"""Comms backends: external notifications for the experiment lifecycle.

Same shape as the ``db``/``writer``/``storage`` layers -- one config key
(``[comms] backend``) resolved through the package catalog, default a
no-op. A backend that fails must never break a running experiment; see
:class:`~flex_exp.experiment.Experiment`, which calls these methods wrapped
in try/except and only logs failures.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CommsBackend(ABC):
    """Notifies an external system (chat, project tracker, ...) of an
    experiment's lifecycle. ``experiment`` is the live
    :class:`~flex_exp.experiment.Experiment`; backends read whatever fields
    they need from it (``.id``, ``.user``, ``.name``, ``.start_time``, ...)."""

    @abstractmethod
    def notify_start(self, experiment: Any) -> Any:
        """Called when an experiment starts. May return backend-specific
        state (e.g. a task id) to hand back via :meth:`notify_end`."""

    @abstractmethod
    def notify_end(self, experiment: Any, state: Any) -> None:
        """Called when an experiment ends, with whatever :meth:`notify_start`
        returned (``None`` if it wasn't called, or itself returned ``None``)."""

    def close(self) -> None:  # noqa: B027 - intentional no-op default, not forgotten abstract
        """Release any held resources (e.g. an HTTP session). No-op by default."""


class NoComms(CommsBackend):
    """The default: no external notifications."""

    def notify_start(self, experiment: Any) -> None:
        return None

    def notify_end(self, experiment: Any, state: Any) -> None:
        pass


#: Comms backend name -> "module:Class" reference.
COMMS: dict[str, str] = {"none": "flex.comms:NoComms"}
