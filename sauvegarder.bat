@echo off
chcp 65001 > nul
echo [SAUVEGARDE] Lancement du protocole de sauvegarde...
python moteur\sauvegarder.py %*
