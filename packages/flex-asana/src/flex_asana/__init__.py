"""Asana comms backend (``[comms] backend = "asana"``): one task per experiment.

Settings come from the environment, or the same-named ``[comms]`` keys
(``access_token``, ``project_gid``, ...) in a flex.toml you don't share:

    ASANA_ACCESS_TOKEN             personal access token (required)
    ASANA_EXPERIMENTS_PROJECT_GID  project the tasks go in (required)
    ASANA_WORKSPACE_GID            only if the account has several workspaces
    ASANA_START_FIELD              custom field for the start, default "Start Time"
    ASANA_END_FIELD                custom field for the end, default "End Time"
"""

COMMS: dict[str, str] = {"asana": "flex_asana.comms:AsanaComms"}
