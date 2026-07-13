import types

from flex_db.sqlite import SQLiteStore
from flex_exp import Experiment
from flex_exp.celllog import CellLogger


class FakeEvents:
    def __init__(self):
        self.registered = None

    def register(self, name, cb):
        self.registered = cb

    def unregister(self, name, cb):
        self.registered = None


class FakeShell:
    def __init__(self):
        self.events = FakeEvents()


def make_result(raw_cell, *, store_history=True, silent=False, execution_count=1, success=True):
    return types.SimpleNamespace(
        info=types.SimpleNamespace(raw_cell=raw_cell, store_history=store_history, silent=silent),
        execution_count=execution_count,
        success=success,
        error_in_exec=None,
    )


def test_real_cell_is_logged(config, tmp_path):
    with Experiment("jane", config=config, cell_log=False) as exp:
        logger = CellLogger(exp, FakeShell())
        logger._log_cell(make_result("x = 1 + 1", execution_count=7))

    store = SQLiteStore(path=tmp_path / "flex.db")
    (cell,) = store.list_cells(exp.id)
    assert cell.source == "x = 1 + 1"
    assert cell.execution_count == 7
    store.close()


def test_background_wrapper_cell_is_not_logged(config, tmp_path):
    """VS Code's Jupyter extension (variable viewer, debugger support) runs
    synthetic code -- async def __jupyter_exec_background__(): ... -- through
    the same post_run_cell event; it should never spam flex_cells."""
    with Experiment("jane", config=config, cell_log=False) as exp:
        logger = CellLogger(exp, FakeShell())
        logger._log_cell(make_result("async def __jupyter_exec_background__():\n    pass"))
        logger._log_cell(make_result("x = 1", store_history=False))
        logger._log_cell(make_result("x = 1", silent=True))
        logger._log_cell(make_result("   \n  "))
        logger._log_cell(make_result(""))

    store = SQLiteStore(path=tmp_path / "flex.db")
    assert store.list_cells(exp.id) == []
    store.close()
