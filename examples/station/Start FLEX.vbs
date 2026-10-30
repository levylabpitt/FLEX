' Starts the FLEX tray app with this folder's flex.toml, without a console window.
Set shell = CreateObject("WScript.Shell")
here = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
shell.Environment("Process")("FLEX_CONFIG") = here & "\flex.toml"
shell.CurrentDirectory = here & "\..\.."
shell.Run "uv run pythonw -m flex app", 0
