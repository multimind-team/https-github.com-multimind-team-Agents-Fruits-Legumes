' Compatibilité : tous les démarrages automatiques passent par le gestionnaire.
Option Explicit
Dim shell, fso, cible, resultat
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
cible = fso.GetParentFolderName(WScript.ScriptFullName) & "\moteur\demarrer-service-local.vbs"
resultat = shell.Run("wscript.exe """ & cible & """", 0, True)
WScript.Quit resultat
