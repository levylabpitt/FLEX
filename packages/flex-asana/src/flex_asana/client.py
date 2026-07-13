"""A thin, typed wrapper around the official Asana Python SDK (v5.x).

Hides the SDK's inconsistent call conventions (some endpoints take the
request body as a positional argument, others expect it nested inside
``opts``), materializes paginated generators into lists, and converts the
SDK's ``ApiException`` into :class:`AsanaError` with logging instead of
silently returning ``None``.

Reads the access token from ``ASANA_ACCESS_TOKEN`` by default::

    client = AsanaClient()                       # uses ASANA_ACCESS_TOKEN
    client = AsanaClient(access_token="2/...")   # explicit
"""

from __future__ import annotations

import os
from typing import Any

import asana
from asana.rest import ApiException

from flex.log import get_logger

log = get_logger("asana.client")

# The Asana API omits most fields unless explicitly requested via opt_fields.
_TASK_FIELDS = (
    "name,resource_type,completed,completed_at,assignee,assignee.name,"
    "due_on,due_at,start_on,notes,projects,projects.name,"
    "memberships,memberships.section,memberships.section.name,"
    "custom_fields,custom_fields.name,custom_fields.display_value,"
    "tags,tags.name,permalink_url,created_at,modified_at"
)
_PROJECT_FIELDS = (
    "name,archived,color,notes,owner,owner.name,current_status,"
    "due_date,start_on,workspace,workspace.name,team,team.name,"
    "permalink_url,created_at,modified_at"
)
_SECTION_FIELDS = "name,created_at,project,project.name"
_STORY_FIELDS = "text,html_text,type,resource_subtype,created_at,created_by,created_by.name"
_USER_FIELDS = "name,email,photo,workspaces,workspaces.name"
_WORKSPACE_FIELDS = "name,is_organization,email_domains"


class AsanaError(RuntimeError):
    """Raised when an Asana API call fails."""


class AsanaClient:
    """High-level client for the Asana REST API.

    Args:
        access_token: Asana Personal Access Token. Falls back to
            ``ASANA_ACCESS_TOKEN`` when omitted.
    """

    def __init__(self, access_token: str | None = None):
        if access_token is None:
            access_token = os.environ.get("ASANA_ACCESS_TOKEN")
        if not access_token:
            raise RuntimeError(
                "Asana access token not provided. Set the ASANA_ACCESS_TOKEN "
                "environment variable or pass access_token explicitly."
            )
        configuration = asana.Configuration()
        configuration.access_token = access_token
        self.api_client = asana.ApiClient(configuration)

        self.tasks = asana.TasksApi(self.api_client)
        self.projects = asana.ProjectsApi(self.api_client)
        self.sections = asana.SectionsApi(self.api_client)
        self.stories = asana.StoriesApi(self.api_client)
        self.users = asana.UsersApi(self.api_client)
        self.workspaces = asana.WorkspacesApi(self.api_client)

    # -- internals -----------------------------------------------------------

    @staticmethod
    def _opts(fields: str | None = None, body: dict | None = None, **extra: Any) -> dict:
        opts: dict = {}
        if fields:
            opts["opt_fields"] = fields
        if body is not None:
            opts["body"] = body
        opts.update({k: v for k, v in extra.items() if v is not None})
        return opts

    @staticmethod
    def _call(func, *args, **kwargs):
        name = getattr(func, "__name__", str(func))
        try:
            return func(*args, **kwargs)
        except ApiException as e:
            log.error("Asana API error in %s: %s", name, e)
            raise AsanaError(f"{name} failed: {e}") from e

    @classmethod
    def _collect(cls, func, *args, **kwargs) -> list:
        result = cls._call(func, *args, **kwargs)
        try:
            return list(result)
        except ApiException as e:
            name = getattr(func, "__name__", str(func))
            log.error("Asana API error while paginating %s: %s", name, e)
            raise AsanaError(f"{name} failed during pagination: {e}") from e

    @staticmethod
    def _data(name: str, value: Any, **fields: Any) -> dict:
        data: dict = {name: value} if name else {}
        data.update({k: v for k, v in fields.items() if v is not None})
        return {"data": data}

    # -- workspaces ------------------------------------------------------------

    def list_workspaces(self) -> list[dict]:
        return self._collect(self.workspaces.get_workspaces, self._opts(_WORKSPACE_FIELDS))

    def get_workspace(self, workspace_gid: str) -> dict:
        return self._call(self.workspaces.get_workspace, workspace_gid, self._opts(_WORKSPACE_FIELDS))

    def default_workspace_gid(self) -> str:
        """The gid of the sole workspace for this account.

        Raises :class:`AsanaError` for zero or multiple workspaces (choose
        explicitly via ``ASANA_WORKSPACE_GID`` in that case).
        """
        workspaces = self.list_workspaces()
        if not workspaces:
            raise AsanaError("No Asana workspaces available for this account.")
        if len(workspaces) > 1:
            options = ", ".join(f"{w.get('name')} ({w.get('gid')})" for w in workspaces)
            raise AsanaError(
                f"Multiple Asana workspaces available; set ASANA_WORKSPACE_GID explicitly. "
                f"Options: {options}"
            )
        return workspaces[0]["gid"]

    # -- users -----------------------------------------------------------------

    def get_user(self, user_gid: str = "me") -> dict:
        return self._call(self.users.get_user, user_gid, self._opts(_USER_FIELDS))

    def me(self) -> dict:
        return self.get_user("me")

    def list_users(self, workspace_gid: str) -> list[dict]:
        return self._collect(
            self.users.get_users_for_workspace, workspace_gid, self._opts(_USER_FIELDS)
        )

    # -- projects --------------------------------------------------------------

    def get_project(self, project_gid: str) -> dict:
        return self._call(self.projects.get_project, project_gid, self._opts(_PROJECT_FIELDS))

    def list_projects(self, workspace_gid: str, archived: bool | None = False) -> list[dict]:
        return self._collect(
            self.projects.get_projects_for_workspace, workspace_gid,
            self._opts(_PROJECT_FIELDS, archived=archived),
        )

    def create_project(
        self, workspace_gid: str, name: str, notes: str | None = None,
        team_gid: str | None = None, **fields: Any,
    ) -> dict:
        """``team_gid`` is required for projects in organization workspaces."""
        body = self._data("name", name, notes=notes, team=team_gid, **fields)
        return self._call(
            self.projects.create_project_for_workspace, body, workspace_gid,
            self._opts(_PROJECT_FIELDS),
        )

    def update_project(self, project_gid: str, **fields: Any) -> dict:
        body = self._data("", None, **fields)
        return self._call(self.projects.update_project, body, project_gid, self._opts(_PROJECT_FIELDS))

    def delete_project(self, project_gid: str) -> dict:
        return self._call(self.projects.delete_project, project_gid)

    def get_project_custom_fields(self, project_gid: str) -> dict[str, str]:
        """{custom_field_name: gid} for a project."""
        project = self._call(
            self.projects.get_project, project_gid,
            self._opts(
                "custom_field_settings,custom_field_settings.custom_field,"
                "custom_field_settings.custom_field.name"
            ),
        )
        result: dict[str, str] = {}
        for setting in project.get("custom_field_settings", []) or []:
            field = setting.get("custom_field", {}) or {}
            name, gid = field.get("name"), field.get("gid")
            if name and gid:
                result[name] = gid
        return result

    def get_project_custom_field_specs(self, project_gid: str) -> dict[str, dict]:
        """{name: {"gid": ..., "type": ...}} where type is the field's
        resource_subtype ("text", "number", "enum", "date", ...)."""
        project = self._call(
            self.projects.get_project, project_gid,
            self._opts(
                "custom_field_settings,custom_field_settings.custom_field,"
                "custom_field_settings.custom_field.name,"
                "custom_field_settings.custom_field.resource_subtype,"
                "custom_field_settings.custom_field.type"
            ),
        )
        specs: dict[str, dict] = {}
        for setting in project.get("custom_field_settings", []) or []:
            field = setting.get("custom_field", {}) or {}
            name, gid = field.get("name"), field.get("gid")
            if name and gid:
                specs[name] = {"gid": gid, "type": field.get("resource_subtype") or field.get("type")}
        return specs

    # -- sections --------------------------------------------------------------

    def list_sections(self, project_gid: str) -> list[dict]:
        return self._collect(self.sections.get_sections_for_project, project_gid, self._opts(_SECTION_FIELDS))

    def create_section(self, project_gid: str, name: str) -> dict:
        """The Sections endpoint takes the request body inside opts."""
        body = self._data("name", name)
        return self._call(
            self.sections.create_section_for_project, project_gid,
            self._opts(_SECTION_FIELDS, body=body),
        )

    def move_task_to_section(self, section_gid: str, task_gid: str) -> dict:
        body = self._data("task", task_gid)
        return self._call(self.sections.add_task_for_section, section_gid, self._opts(body=body))

    # -- tasks -------------------------------------------------------------------

    def get_task(self, task_gid: str) -> dict:
        return self._call(self.tasks.get_task, task_gid, self._opts(_TASK_FIELDS))

    def list_tasks_for_project(self, project_gid: str, completed_since: str | None = None) -> list[dict]:
        """``completed_since``: ISO 8601 timestamp or "now" to limit to
        incomplete tasks or ones completed after that time."""
        return self._collect(
            self.tasks.get_tasks_for_project, project_gid,
            self._opts(_TASK_FIELDS, completed_since=completed_since),
        )

    def create_task(
        self, project_gid: str, name: str, notes: str | None = None,
        assignee: str | None = None, due_on: str | None = None,
        custom_fields: dict | None = None, **fields: Any,
    ) -> dict:
        """``assignee``: user gid or email. ``custom_fields``: {gid: value}."""
        body = self._data(
            "name", name, projects=[project_gid], notes=notes,
            assignee=assignee, due_on=due_on, custom_fields=custom_fields, **fields,
        )
        return self._call(self.tasks.create_task, body, self._opts(_TASK_FIELDS))

    def update_task(self, task_gid: str, **fields: Any) -> dict:
        body = self._data("", None, **fields)
        return self._call(self.tasks.update_task, body, task_gid, self._opts(_TASK_FIELDS))

    def complete_task(self, task_gid: str) -> dict:
        return self.update_task(task_gid, completed=True)

    def delete_task(self, task_gid: str) -> dict:
        return self._call(self.tasks.delete_task, task_gid)

    def add_followers(self, task_gid: str, follower_gids: list[str]) -> dict:
        body = self._data("followers", follower_gids)
        return self._call(self.tasks.add_followers_for_task, body, task_gid, self._opts(_TASK_FIELDS))

    def add_task_to_project(self, task_gid: str, project_gid: str, section_gid: str | None = None) -> dict:
        body = self._data("project", project_gid, section=section_gid)
        return self._call(self.tasks.add_project_for_task, body, task_gid)

    # -- stories (comments) ------------------------------------------------------

    def list_comments(self, task_gid: str) -> list[dict]:
        return self._collect(self.stories.get_stories_for_task, task_gid, self._opts(_STORY_FIELDS))

    def add_comment(self, task_gid: str, text: str) -> dict:
        body = self._data("text", text)
        return self._call(self.stories.create_story_for_task, body, task_gid, self._opts(_STORY_FIELDS))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(authenticated)"


#: Historical alias.
Asana = AsanaClient
