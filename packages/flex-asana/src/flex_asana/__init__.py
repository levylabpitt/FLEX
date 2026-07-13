"""Asana comms backend: one Asana task per experiment, via the Asana API
directly (no n8n or other middleman).

Enable it in an ecosystem manifest::

    [comms]
    backend = "asana"

Configuration is read from the environment (never the manifest, since these
aren't secrets so much as per-account specifics that don't belong committed
to a shared repo):

    ASANA_ACCESS_TOKEN            # personal access token (required)
    ASANA_WORKSPACE_GID           # optional if the account has one workspace
    ASANA_EXPERIMENTS_PROJECT_GID # project experiment tasks are created in (required)
    ASANA_START_FIELD             # custom field name, default "Start Time"
    ASANA_END_FIELD               # custom field name, default "End Time"

A missing token or project gid is logged as a warning and the experiment
continues without Asana sync — see flex_exp.Experiment, which builds and
calls this backend wrapped in try/except.

``User`` (from ``flex_asana.users``) is a `Literal` of workspace handles once
generated (``python -m flex_asana.update_users``); flex-exp uses it for
``Experiment(user=...)`` autocomplete, falling back to plain ``str`` before
first generation or if flex-asana isn't installed at all.
"""

from flex_asana.client import Asana, AsanaClient, AsanaError
from flex_asana.comms import AsanaComms
from flex_asana.sync import ExperimentSync, handle_from_user
from flex_asana.users import User

__version__ = "2.0.0a1"

#: Comms backend name -> "module:Class" reference.
COMMS: dict[str, str] = {"asana": "flex_asana.comms:AsanaComms"}

__all__ = [
    "COMMS",
    "Asana",
    "AsanaClient",
    "AsanaComms",
    "AsanaError",
    "ExperimentSync",
    "User",
    "handle_from_user",
]
