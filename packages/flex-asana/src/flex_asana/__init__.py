"""FLEX hooks for Asana project tracking, via the lab's n8n automation.

Configuration (in the ecosystem manifest)::

    [asana]
    webhook_url = "https://n8n.example.org/webhook/<id>"

    [hooks]
    on_experiment_start = ["flex_asana.hooks:notify_n8n"]
    on_experiment_end   = ["flex_asana.hooks:notify_n8n"]

The webhook URL may also be set via the ``FLEX_N8N_WEBHOOK`` environment
variable. Credentials are never stored in code.
"""

__version__ = "2.0.0a1"
