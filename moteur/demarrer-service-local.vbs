' Demarrage automatique silencieux de l'application preparation-commande au demarrage de Windows.
' Lance le serveur (port 8751), sa surveillance et la sentinelle mail/messages/comptages sans ouvrir de fenetre noire.

Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

dossierProjet = "C:\Users\user\Desktop\preparation-commande-dev"
pythonExe = "C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe"
pythonwExe = "C:\Users\user\AppData\Local\Programs\Python\Python314\pythonw.exe"

If Not fso.FileExists(pythonExe) Then
    pythonExe = "python.exe"
    pythonwExe = "pythonw.exe"
End If

' 1. Verifier si le serveur 8751 repond deja
Dim http, serveurActif
serveurActif = False
On Error Resume Next
Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
http.Open "GET", "http://127.0.0.1:8751/app/index.html", False
http.setTimeouts 2000, 2000, 2000, 2000
http.Send
If Err.Number = 0 And http.Status = 200 Then
    serveurActif = True
End If
On Error GoTo 0

' 2. Si le serveur n'est pas actif, le lancer
If Not serveurActif Then
    cmdServeur = """" & pythonExe & """ """ & dossierProjet & "\moteur\serveur.py"" 8751"
    shell.CurrentDirectory = dossierProjet
    shell.Run "%comspec% /c " & cmdServeur & " >> """ & dossierProjet & "\serveur.log"" 2>> """ & dossierProjet & "\serveur-erreurs.log""", 0, False
    WScript.Sleep 2500
End If

' 3. Lancer la surveillance automatique du serveur (si pas deja active)
cmdSurveillance = """" & pythonwExe & """ """ & dossierProjet & "\moteur\surveiller-serveur.py"" --intervalle 30 --port 8751"
shell.CurrentDirectory = dossierProjet
shell.Run cmdSurveillance, 0, False
