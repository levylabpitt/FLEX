"""Creates/updates an Asana task per experiment: start time on create, end
time filled in on end. The user's Asana gid is resolved from the workspace
member list (email local-part, falling back to a dotted name handle).
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from flex.log import get_logger
from flex_asana.client import AsanaClient

log = get_logger("asana.sync")


def handle_from_user(user: dict) -> str | None:
    """FLEX username handle from an Asana user record: email local-part
    (``pubudu.wijesinghe@levylab.org`` -> ``pubudu.wijesinghe``), falling back
    to the display name lowercased with spaces replaced by dots."""
    email = (user.get("email") or "").strip().lower()
    if email:
        return email.split("@")[0]
    name = (user.get("name") or "").strip().lower()
    if name:
        return name.replace(" ", ".")
    return None


class ExperimentSync:
    """Args:
        client: Pre-built client; created from the environment if omitted.
        workspace_gid, project_gid: Override ``ASANA_WORKSPACE_GID`` /
            ``ASANA_EXPERIMENTS_PROJECT_GID``.
        start_field, end_field: Names of the date custom fields for the
            start/end timestamps.
        assign_user: Assign the created task to the experiment's user.
    """

    def __init__(
        self,
        client: AsanaClient | None = None,
        workspace_gid: str | None = None,
        project_gid: str | None = None,
        start_field: str | None = None,
        end_field: str | None = None,
        assign_user: bool = True,
    ):
        self.client = client or AsanaClient()
        self.workspace_gid = workspace_gid or os.environ.get("ASANA_WORKSPACE_GID")
        if not self.workspace_gid:
            self.workspace_gid = self.client.default_workspace_gid()
        self.project_gid = project_gid or os.environ.get("ASANA_EXPERIMENTS_PROJECT_GID")
        if not self.project_gid:
            raise ValueError(
                "Asana experiments project gid required. Set "
                "ASANA_EXPERIMENTS_PROJECT_GID or pass project_gid=."
            )
        self.start_field = start_field or os.environ.get("ASANA_START_FIELD", "Start Time")
        self.end_field = end_field or os.environ.get("ASANA_END_FIELD", "End Time")
        self.assign_user = assign_user

        self._user_map: dict[str, str] | None = None
        self._field_specs: dict[str, dict] | None = None

    # -- lazy lookups, cached on the instance --------------------------------

    def _users(self) -> dict[str, str]:
        if self._user_map is None:
            self._user_map = {}
            for user in self.client.list_users(self.workspace_gid):
                handle = handle_from_user(user)
                gid = user.get("gid")
                if handle and gid:
                    self._user_map[handle] = gid
        return self._user_map

    def resolve_user_gid(self, handle: str) -> str | None:
        gid = self._users().get(handle.lower())
        if gid is None:
            log.warning("No Asana user found for handle '%s'.", handle)
        return gid

    def _fields(self) -> dict[str, dict]:
        if self._field_specs is None:
            self._field_specs = self.client.get_project_custom_field_specs(self.project_gid)
        return self._field_specs

    def _custom_field_value(self, field_name: str, when: datetime) -> tuple[str | None, Any]:
        """(gid, value) for a timestamp formatted to the field's type, or
        (None, None) if the field is missing."""
        spec = self._fields().get(field_name)
        if not spec:
            log.warning("Custom field '%s' not found in project %s; skipping.", field_name, self.project_gid)
            return None, None
        ftype = spec.get("type")
        if ftype == "date":
            value = {"date_time": when.astimezone().isoformat()}
        else:
            if ftype != "text":
                log.warning("Custom field '%s' is type '%s'; writing as text.", field_name, ftype)
            value = when.isoformat(sep=" ", timespec="seconds")
        return spec["gid"], value

    # -- public API -----------------------------------------------------------

    def start_experiment(self, user_handle: str, name: str, start_time: datetime, notes: str = "") -> str | None:
        """Create the experiment task and return its gid."""
        custom_fields = {}
        gid, value = self._custom_field_value(self.start_field, start_time)
        if gid is not None:
            custom_fields[gid] = value

        assignee = self.resolve_user_gid(user_handle) if self.assign_user else None

        task = self.client.create_task(
            self.project_gid, name, notes=notes or None, assignee=assignee,
            custom_fields=custom_fields or None,
        )
        return task.get("gid")

    def end_experiment(self, task_gid: str, end_time: datetime) -> None:
        """Fill in the end-time custom field on an existing experiment task."""
        gid, value = self._custom_field_value(self.end_field, end_time)
        if gid is None:
            return
        self.client.update_task(task_gid, custom_fields={gid: value})
