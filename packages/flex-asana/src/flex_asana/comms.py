"""The ``asana`` comms backend: one Asana task per experiment."""

from __future__ import annotations

from typing import Any

from flex.comms import CommsBackend
from flex_asana.client import AsanaClient
from flex_asana.sync import ExperimentSync


class AsanaComms(CommsBackend):
    """Creates an Asana task when an experiment starts (stamped with the
    start time, assigned to the user) and fills in the end time when it
    ends. See :class:`~flex_asana.sync.ExperimentSync` for the env vars
    this reads (``ASANA_ACCESS_TOKEN``, ``ASANA_WORKSPACE_GID``,
    ``ASANA_EXPERIMENTS_PROJECT_GID``, ``ASANA_START_FIELD``, ``ASANA_END_FIELD``).
    Any argument here overrides the matching env var.
    """

    def __init__(
        self,
        *,
        access_token: str | None = None,
        workspace_gid: str | None = None,
        project_gid: str | None = None,
        start_field: str | None = None,
        end_field: str | None = None,
        assign_user: bool = True,
    ):
        self._sync = ExperimentSync(
            client=AsanaClient(access_token),
            workspace_gid=workspace_gid,
            project_gid=project_gid,
            start_field=start_field,
            end_field=end_field,
            assign_user=assign_user,
        )

    def notify_start(self, experiment: Any) -> str | None:
        name = f"Experiment {experiment.id} ({experiment.user})"
        return self._sync.start_experiment(experiment.user, name, experiment.start_time)

    def notify_end(self, experiment: Any, state: str | None) -> None:
        if state is None:
            return
        self._sync.end_experiment(state, experiment.end_time)
