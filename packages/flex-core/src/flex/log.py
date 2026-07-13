"""FLEX logging.

All framework loggers live under the ``flex`` namespace. The root logger is
never configured here, so FLEX coexists cleanly with any application logging.
"""

from __future__ import annotations

import logging
from pathlib import Path

_ROOT = "flex"
_FILE_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"

_console_handler: logging.Handler | None = None


def get_logger(name: str = "") -> logging.Logger:
    """Return a logger under the ``flex`` namespace (e.g. ``get_logger("inst.lockin")``)."""
    return logging.getLogger(f"{_ROOT}.{name}" if name else _ROOT)


def is_interactive() -> bool:
    """Running under IPython (Jupyter, or VS Code's Interactive Window)?"""
    try:
        from IPython import get_ipython
    except ImportError:
        return False
    return get_ipython() is not None


def enable_console(level: int | None = None) -> logging.Handler:
    """Attach a single rich console handler to the ``flex`` logger. Idempotent.

    Interactive sessions (Jupyter / VS Code Interactive Window) default to
    WARNING: routine per-instrument INFO chatter reads fine in a terminal but
    clutters a notebook cell, where the point is one glanceable HTML summary
    instead (see Experiment._repr_html_ / CESession._repr_html_).
    """
    global _console_handler
    logger = get_logger()
    logger.setLevel(logging.DEBUG)
    if level is None:
        level = logging.WARNING if is_interactive() else logging.INFO
    if _console_handler is None:
        from rich.logging import RichHandler

        _console_handler = RichHandler(show_path=False, rich_tracebacks=False)
        logger.addHandler(_console_handler)
    _console_handler.setLevel(level)
    return _console_handler


def add_file_log(path: str | Path, level: int = logging.DEBUG) -> logging.Handler:
    """Attach a file handler to the ``flex`` logger (e.g. one file per experiment).

    Returns the handler; pass it to :func:`remove_log_handler` when done.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FILE_FORMAT))
    logger = get_logger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    return handler


def remove_log_handler(handler: logging.Handler) -> None:
    """Detach and close a handler previously returned by :func:`add_file_log`."""
    get_logger().removeHandler(handler)
    handler.close()
