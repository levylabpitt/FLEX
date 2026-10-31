"""Thin wrapper over the Asana SDK v5: paginated results become lists, ApiException becomes
:class:`AsanaError`. The token defaults to ``ASANA_ACCESS_TOKEN``."""

from __future__ import annotations

import os
from typing import Any

import asana
from asana.rest import ApiException

from flex.log import get_logger

log = get_logger("asana.client")

# the API omits most fields unless requested through opt_fields
_USER_FIELDS = "name,email"
_WORKSPACE_FIELDS = "name"


class AsanaError(RuntimeError):
    """An Asana API call failed."""


class AsanaClient:
    def __init__(self, access_token: str | None = None):
        access_token = access_token or os.environ.get("ASANA_ACCESS_TOKEN")
        if not access_token:
            raise RuntimeError("Asana access token missing: set ASANA_ACCESS_TOKEN or pass access_token")
        configuration = asana.Configuration()
        configuration.access_token = access_token
        api = asana.ApiClient(configuration)
        self.tasks = asana.TasksApi(api)
        self.projects = asana.ProjectsApi(api)
        self.users = asana.UsersApi(api)
        self.workspaces = asana.WorkspacesApi(api)

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _call(func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ApiException as e:
            name = getattr(func, "__name__", str(func))
            log.error("Asana API error in %s: %s", name, e)
            raise AsanaError(f"{name} failed: {e}") from e

    @classmethod
    def _collect(cls, func, *args, **kwargs) -> list:
        result = cls._call(func, *args, **kwargs)
        try:
            return list(result)
        except ApiException as e:
            raise AsanaError(f"{getattr(func, '__name__', func)} failed during pagination: {e}") from e

    @staticmethod
    def _data(**fields: Any) -> dict:
        return {"data": {k: v for k, v in fields.items() if v is not None}}

    # -- API -------------------------------------------------------------------

    def list_workspaces(self) -> list[dict]:
        return self._collect(self.workspaces.get_workspaces, {"opt_fields": _WORKSPACE_FIELDS})

    def default_workspace_gid(self) -> str:
        """The account's only workspace; set ASANA_WORKSPACE_GID when there are several."""
        workspaces = self.list_workspaces()
        if not workspaces:
            raise AsanaError("No Asana workspaces available for this account.")
        if len(workspaces) > 1:
            options = ", ".join(f"{w.get('name')} ({w.get('gid')})" for w in workspaces)
            raise AsanaError(f"Multiple Asana workspaces available; set ASANA_WORKSPACE_GID explicitly. Options: {options}")
        return workspaces[0]["gid"]

    def list_users(self, workspace_gid: str) -> list[dict]:
        return self._collect(self.users.get_users_for_workspace, workspace_gid, {"opt_fields": _USER_FIELDS})

    def get_project_custom_field_specs(self, project_gid: str) -> dict[str, dict]:
        """{field name: {"gid", "type"}}; type is "text", "number", "enum", "date", ..."""
        project = self._call(
            self.projects.get_project, project_gid,
            {"opt_fields": "custom_field_settings.custom_field.name,"
                           "custom_field_settings.custom_field.resource_subtype,"
                           "custom_field_settings.custom_field.type"},
        )
        specs: dict[str, dict] = {}
        for setting in project.get("custom_field_settings", []) or []:
            field = setting.get("custom_field", {}) or {}
            name, gid = field.get("name"), field.get("gid")
            if name and gid:
                specs[name] = {"gid": gid, "type": field.get("resource_subtype") or field.get("type")}
        return specs

    def create_task(self, project_gid: str, name: str, *, assignee: str | None = None,
                    custom_fields: dict | None = None) -> dict:
        """``assignee``: user gid or email. ``custom_fields``: {gid: value}."""
        body = self._data(name=name, projects=[project_gid], assignee=assignee, custom_fields=custom_fields)
        return self._call(self.tasks.create_task, body, {"opt_fields": "gid"})

    def update_task(self, task_gid: str, **fields: Any) -> dict:
        return self._call(self.tasks.update_task, self._data(**fields), task_gid, {"opt_fields": "gid"})
