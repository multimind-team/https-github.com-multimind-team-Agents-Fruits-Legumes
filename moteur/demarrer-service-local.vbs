' Démarrage Windows silencieux du serveur et de sa surveillance.
' La Tri-Sentinelle est un processus distinct, piloté par l'agent.
Option Explicit
Dim shell, fso, dossierProjet, commande, resultat
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dossierProjet = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
shell.CurrentDirectory = dossierProjet
commande = "py -3.14 """ & dossierProjet & "\moteur\gerer-serveur.py"" demarrer --automatique --silencieux"
resultat = shell.Run(commande, 0, True)
WScript.Quit resultat
