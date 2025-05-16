import asana
from asana.rest import ApiException

access_token_n8nio = '2/1209143437361178/1209900811683018:c9f650887bd79379c1ab13cf3f4eeed1'

class Asana:
    def __init__(self, access_token=access_token_n8nio):
        configuration = asana.Configuration()
        configuration.access_token = access_token
        self.api_client = asana.ApiClient(configuration)

    def get_project_data(self, project_gid, opts=None):
        self.project_gid = project_gid
        self.projects_api_instance = asana.ProjectsApi(self.api_client)
        self.project_data = None
        if opts is None:
            opts = {
                'opt_fields': "archived,color,completed,completed_at,completed_by,completed_by.name,"
                              "created_at,created_from_template,created_from_template.name,current_status,"
                              "current_status.author,current_status.author.name,current_status.color,"
                              "current_status.created_at,current_status.created_by,current_status.created_by.name,"
                              "current_status.html_text,current_status.modified_at,current_status.text,"
                              "current_status.title,current_status_update,current_status_update.resource_subtype,"
                              "current_status_update.title,custom_field_settings,custom_field_settings.custom_field,"
                              "custom_field_settings.custom_field.asana_created_field,custom_field_settings.custom_field.created_by,"
                              "custom_field_settings.custom_field.created_by.name,custom_field_settings.custom_field.currency_code,"
                              "custom_field_settings.custom_field.custom_label,custom_field_settings.custom_field.custom_label_position,"
                              "custom_field_settings.custom_field.date_value,custom_field_settings.custom_field.date_value.date,"
                              "custom_field_settings.custom_field.date_value.date_time,custom_field_settings.custom_field.default_access_level,"
                              "custom_field_settings.custom_field.description,custom_field_settings.custom_field.display_value,"
                              "custom_field_settings.custom_field.enabled,custom_field_settings.custom_field.enum_options,"
                              "custom_field_settings.custom_field.enum_options.color,custom_field_settings.custom_field.enum_options.enabled,"
                              "custom_field_settings.custom_field.enum_options.name,custom_field_settings.custom_field.enum_value,"
                              "custom_field_settings.custom_field.enum_value.color,custom_field_settings.custom_field.enum_value.enabled,"
                              "custom_field_settings.custom_field.enum_value.name,custom_field_settings.custom_field.format,"
                              "custom_field_settings.custom_field.has_notifications_enabled,custom_field_settings.custom_field.id_prefix,"
                              "custom_field_settings.custom_field.is_formula_field,custom_field_settings.custom_field.is_global_to_workspace,"
                              "custom_field_settings.custom_field.is_value_read_only,custom_field_settings.custom_field.multi_enum_values,"
                              "custom_field_settings.custom_field.multi_enum_values.color,custom_field_settings.custom_field.multi_enum_values.enabled,"
                              "custom_field_settings.custom_field.multi_enum_values.name,custom_field_settings.custom_field.name,"
                              "custom_field_settings.custom_field.number_value,custom_field_settings.custom_field.people_value,"
                              "custom_field_settings.custom_field.people_value.name,custom_field_settings.custom_field.precision,"
                              "custom_field_settings.custom_field.privacy_setting,custom_field_settings.custom_field.representation_type,"
                              "custom_field_settings.custom_field.resource_subtype,custom_field_settings.custom_field.text_value,"
                              "custom_field_settings.custom_field.type,custom_field_settings.is_important,custom_field_settings.parent,"
                              "custom_field_settings.parent.name,custom_field_settings.project,custom_field_settings.project.name,"
                              "custom_fields,custom_fields.date_value,custom_fields.date_value.date,custom_fields.date_value.date_time,"
                              "custom_fields.display_value,custom_fields.enabled,custom_fields.enum_options,custom_fields.enum_options.color,"
                              "custom_fields.enum_options.enabled,custom_fields.enum_options.name,custom_fields.enum_value,"
                              "custom_fields.enum_value.color,custom_fields.enum_value.enabled,custom_fields.enum_value.name,"
                              "custom_fields.id_prefix,custom_fields.is_formula_field,custom_fields.multi_enum_values,"
                              "custom_fields.multi_enum_values.color,custom_fields.multi_enum_values.enabled,custom_fields.multi_enum_values.name,"
                              "custom_fields.name,custom_fields.number_value,custom_fields.representation_type,custom_fields.text_value,"
                              "custom_fields.type,default_access_level,default_view,due_date,due_on,followers,followers.name,html_notes,"
                              "icon,members,members.name,minimum_access_level_for_customization,minimum_access_level_for_sharing,"
                              "modified_at,name,notes,owner,permalink_url,privacy_setting,project_brief,public,start_on,team,team.name,"
                              "workspace,workspace.name"
            }
        
        try:
            self.project_data = self.projects_api_instance.get_project(self.project_gid, opts)
        except ApiException as e:
            print(f"Exception when calling ProjectsApi->get_project: {e}")
        
        return self.project_data

    def get_project_custom_fields_gids(self, project_gid):
        """Extract custom field names and their GIDs from project data"""
        self.get_project_data(project_gid=project_gid)  # Ensure project data is fetched
        if not self.project_data:
            print("Project data not fetched yet. Call get_project_data() first.")
            return None

        custom_fields = {}
        for field in self.project_data.get("custom_field_settings", []):
            custom_field = field.get("custom_field", {})
            gid = custom_field.get("gid")
            name = custom_field.get("name")
            custom_fields[name] = gid
        
        return custom_fields
    
    def create_task_in_project(self, project_gid, task_name):
        tasks_api_instance = asana.TasksApi(self.api_client)
        body = {
            "data": {
                "name": task_name,
                "projects": [project_gid],
                "custom_fields": {}
            }
        }
        
        try:
            api_response = tasks_api_instance.create_task(body, {})
            print(f"Task '{task_name}' created in project {project_gid}.")
            return api_response
        except ApiException as e:
            print(f"Exception when calling TasksApi->create_task: {e}")
            return None

if __name__ == "__main__":
    project_gid = "1209900702466701"
    a = Asana()
    print(a.get_project_custom_fields_gids(project_gid))
    a.create_task_in_project(project_gid, "testing function")
