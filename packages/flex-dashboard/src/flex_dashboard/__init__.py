"""FLEX dashboard: a local web UI over the FLEX package manager, ecosystem
configuration, station instruments, and experiment records.

Launch with ``flex dashboard`` (or ``python -m flex_dashboard``).
"""

from __future__ import annotations

__version__ = "2.0.0a1"


def run(host: str = "127.0.0.1", port: int = 8756) -> None:
    """Start the dashboard server (blocking)."""
    import uvicorn

    from flex_dashboard.app import create_app

    print(f"FLEX dashboard: http://{host}:{port}")
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")
