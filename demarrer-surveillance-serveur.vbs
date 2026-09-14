' Démarre la surveillance silencieuse du serveur de préparation de commande.
Set shell = CreateObject("WScript.Shell")
shell.Run """C:\Users\user\AppData\Local\Programs\Python\Python314\pythonw.exe"" ""C:\Users\user\Desktop\preparation-commande\moteur\surveiller-serveur.py"" --intervalle 30", 0, False
