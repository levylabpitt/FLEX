"""Event hooks that notify the lab's n8n automation (which updates Asana)."""

from __future__ import annotations

import os
from typing import Any

import requests

from flex.log import get_logger

log = get_logger("asana")

_TIMEOUT = 5.0


def _webhook_url(experiment: Any) -> str | None:
    if experiment is not None:
        section = (experiment.config.model_extra or {}).get("asana") or {}
        if isinstance(section, dict) and section.get("webhook_url"):
            return section["webhook_url"]
    return os.environ.get("FLEX_N8N_WEBHOOK")


def notify_n8n(event: str, experiment: Any = None, **_payload: Any) -> None:
    """POST an experiment lifecycle event to the configured n8n webhook.

    Subscribe via the ecosystem manifest (see package docstring). Failures are
    logged and swallowed — a webhook must never break an experiment.
    """
    url = _webhook_url(experiment)
    if not url:
        log.warning("No n8n webhook configured ([asana] webhook_url or FLEX_N8N_WEBHOOK); skipping")
        return
    body = {"event": event}
    if experiment is not None:
        body.update(
            experiment_id=experiment.id,
            user=experiment.user,
            name=experiment.name,
            start_time=str(experiment.start_time),
            end_time=str(experiment.end_time) if experiment.end_time else None,
        )
    try:
        response = requests.post(url, json=body, timeout=_TIMEOUT)
        if response.ok:
            log.info("n8n notified: %s (%s)", event, response.status_code)
        else:
            log.warning("n8n webhook returned %s for %s", response.status_code, event)
    except requests.RequestException as e:
        log.warning("n8n webhook unreachable: %s", e)
