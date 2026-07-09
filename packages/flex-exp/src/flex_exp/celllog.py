"""Jupyter cell logging: every executed cell becomes a note on the experiment,
so the exact code that produced a dataset is always recoverable."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from flex.metadata import NoteRecord

if TYPE_CHECKING:
    from flex_exp.experiment import Experiment


class CellLogger:
    @classmethod
    def attach(cls, experiment: Experiment) -> CellLogger | None:
        """Attach to the running IPython shell; returns None outside IPython."""
        try:
            from IPython import get_ipython
        except ImportError:
            return None
        shell = get_ipython()
        if shell is None:
            return None
        return cls(experiment, shell)

    def __init__(self, experiment: Experiment, shell):
        self.experiment = experiment
        self.shell = shell
        self.counter = 0
        shell.events.register("post_run_cell", self._log_cell)

    def _log_cell(self, result) -> None:
        try:
            code = result.info.raw_cell
            self.counter += 1
            self.experiment._record(
                lambda db: db.record_note(
                    NoteRecord(
                        experiment_id=self.experiment.id,
                        text=code,
                        time=datetime.now(),
                        kind="cell",
                    )
                )
            )
        except Exception:
            self.experiment.log.exception("Cell logging failed (ignored)")

    def detach(self) -> None:
        try:
            self.shell.events.unregister("post_run_cell", self._log_cell)
        except ValueError:
            pass
