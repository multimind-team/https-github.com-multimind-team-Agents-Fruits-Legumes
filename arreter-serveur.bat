@echo off
setlocal
cd /d "%~dp0"
rem Arrete seulement les scripts identifies de CE projet, surveillance d'abord.
rem L'arret persiste a la prochaine session ; reprise : demarrer-serveur.bat.
set "SILENCIEUX="
for %%A in (%*) do if /I "%%~A"=="--silencieux" set "SILENCIEUX=1"
py -3.14 "%~dp0moteur\gerer-serveur.py" arreter %*
set "RESULTAT=%ERRORLEVEL%"
echo.
if not defined SILENCIEUX pause
exit /b %RESULTAT%
