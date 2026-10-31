' Starts the FLEX tray app without a console window, with FLEX_CONFIG if set,
' else this folder's flex.toml.
Set shell = CreateObject("WScript.Shell")
here = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
If shell.ExpandEnvironmentStrings("%FLEX_CONFIG%") = "%FLEX_CONFIG%" Then shell.Environment("Process")("FLEX_CONFIG") = here & "\flex.toml"
shell.CurrentDirectory = here & "\..\.."
shell.Run "uv run pythonw -m flex app", 0
