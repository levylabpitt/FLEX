"""Shared HTML representations for Jupyter / VS Code interactive windows.

One consistent look for every FLEX object (generalized from the v1 CESession
summary card). Plain-text ``__repr__`` remains the fallback everywhere.
"""

from __future__ import annotations

from html import escape
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from flex.instrument.base import Instrument

_CSS = """
<style>
    .flex-card {
        font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace;
        font-size: 13px;
        background: #0f172a;
        color: #e2e8f0;
        border-radius: 10px;
        padding: 18px 22px;
        max-width: 760px;
    }
    .flex-card .header {
        font-size: 11px;
        letter-spacing: 3px;
        color: #4ade80;
        text-transform: uppercase;
        margin-bottom: 12px;
    }
    .flex-card .header::before { content: '\\25CF  '; }
    .flex-card .meta-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 6px 24px;
        margin-bottom: 8px;
    }
    .flex-card .meta-item { display: flex; flex-direction: column; }
    .flex-card .meta-label {
        font-size: 9px;
        letter-spacing: 2px;
        color: #64748b;
        text-transform: uppercase;
    }
    .flex-card .meta-value { font-size: 13px; color: #f1f5f9; font-weight: 600; }
    .flex-card .section {
        font-size: 9px;
        letter-spacing: 2px;
        color: #64748b;
        text-transform: uppercase;
        margin: 14px 0 6px;
    }
    .flex-card table { width: 100%; border-collapse: collapse; font-size: 12px; }
    .flex-card th {
        text-align: left;
        padding: 6px 10px;
        font-size: 9px;
        letter-spacing: 2px;
        color: #64748b;
        border-bottom: 1px solid #1e293b;
        text-transform: uppercase;
    }
    .flex-card td {
        text-align: left;
        padding: 6px 10px;
        color: #94a3b8;
        border-bottom: 1px solid #1e293b;
    }
    .flex-card td:first-child { color: #e2e8f0; font-weight: 600; }
    .flex-card .ok { color: #4ade80; }
    .flex-card .bad { color: #f87171; font-style: italic; }
    .flex-card code {
        font-size: 11px;
        color: #94a3b8;
        background: #1e293b;
        padding: 2px 6px;
        border-radius: 3px;
    }
</style>
"""


def card(header: str, meta: dict[str, Any], sections: list[tuple[str, str]] | None = None) -> str:
    """Build a FLEX card: a header, a key/value grid, and optional table sections."""
    items = "".join(
        f'<div class="meta-item"><span class="meta-label">{escape(str(k))}</span>'
        f'<span class="meta-value">{escape(str(v))}</span></div>'
        for k, v in meta.items()
    )
    body = "".join(
        f'<div class="section">{escape(title)}</div>{table_html}'
        for title, table_html in (sections or [])
    )
    return (
        f'{_CSS}<div class="flex-card"><div class="header">{escape(header)}</div>'
        f'<div class="meta-grid">{items}</div>{body}</div>'
    )


def table(headers: list[str], rows: list[list[str]]) -> str:
    """An HTML table body for use inside :func:`card` sections. Cells may
    contain pre-built HTML (escape values yourself where needed)."""
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def auto_display(obj: Any) -> str | None:
    """Push ``obj._repr_html_()`` to a live Jupyter/VS Code Interactive
    display, returning a display id to keep it updated with
    :func:`refresh_display`. Outside an interactive session (plain scripts,
    terminals) this is a no-op returning ``None``.

    An object's own ``_repr_html_`` only renders automatically when it's the
    *last expression* of a cell -- useless for ``with Experiment(...) as exp:``,
    where the object is never that. This pushes it explicitly instead.
    """
    from flex.log import is_interactive

    if not is_interactive():
        return None
    from IPython.display import HTML, display

    handle = display(HTML(obj._repr_html_()), display_id=True)
    return handle.display_id


def refresh_display(obj: Any, display_id: str | None) -> None:
    """Re-render ``obj._repr_html_()`` into a display started by
    :func:`auto_display`. No-op if ``display_id`` is ``None`` (non-interactive,
    or auto_display was never called)."""
    if display_id is None:
        return
    from IPython.display import HTML, update_display

    update_display(HTML(obj._repr_html_()), display_id=display_id)


def instrument_html(instrument: Instrument) -> str:
    rows = []
    for name, p in instrument.parameters.items():
        access = ("get" if p.gettable else "") + ("/set" if p.settable else "")
        rows.append([escape(name), escape(p.unit or "—"), escape(access.strip("/") or "—")])
    sections = [("Parameters", table(["Name", "Unit", "Access"], rows))] if rows else []
    return card(
        f"{type(instrument).__name__}",
        {"Name": instrument.name, "Address": instrument.address or "—"},
        sections,
    )
