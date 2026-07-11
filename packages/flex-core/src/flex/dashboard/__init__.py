"""FLEX dashboard: a local web UI over the package manager, ecosystem
configuration, station instruments, and experiment records.

Launch with ``flex dashboard`` (or ``python -m flex.dashboard``).
"""

from __future__ import annotations

__all__ = ["run"]


def run(host: str = "127.0.0.1", port: int = 8756) -> None:
    """Start the dashboard server (blocking)."""
    import uvicorn

    from flex.dashboard.app import create_app

    print(f"FLEX dashboard: http://{host}:{port}")
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")
