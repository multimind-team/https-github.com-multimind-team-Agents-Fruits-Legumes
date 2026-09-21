Option Explicit
Dim shell, files, root, command
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
root = files.GetParentFolderName(WScript.ScriptFullName)
command = "py -3.14 -B """ & root & "\moteur\ouvrir-cockpit.py"""
shell.Run command, 0, False
