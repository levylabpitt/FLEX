"""Jupyter cell logging: every executed cell becomes a `flex_cells` row, so
the exact code that produced a dataset is always recoverable."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from flex.metadata import CellRecord

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
        shell.events.register("post_run_cell", self._log_cell)

    def _log_cell(self, result) -> None:
        try:
            info = result.info
            raw_cell = info.raw_cell
            # Tools built on the kernel (VS Code's Jupyter extension, variable
            # viewers, debugger support) run synthetic code -- e.g. wrapped in
            # `async def __jupyter_exec_background__(): ...` -- via the same
            # post_run_cell event. Those runs set store_history=False (or are
            # silent) and aren't a cell the user actually wrote; skip them, as
            # well as no-op blank cells.
            if not getattr(info, "store_history", True) or getattr(info, "silent", False):
                return
            if not raw_cell or not raw_cell.strip():
                return
            if "__jupyter_exec_background__" in raw_cell:
                return

            error = str(result.error_in_exec) if result.error_in_exec else None
            self.experiment._record(
                lambda db: db.record_cell(
                    CellRecord(
                        experiment_id=self.experiment.id,
                        source=raw_cell,
                        time=datetime.now(),
                        execution_count=result.execution_count,
                        success=result.success,
                        error=error,
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
