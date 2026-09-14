@echo off
setlocal
cd /d "%~dp0"
rem Conserve le serveur sain. Maintenance explicite : --redemarrer.
rem Identite du script, sante HTTP et surveillance sont verifies ensemble.
set "SILENCIEUX="
for %%A in (%*) do if /I "%%~A"=="--silencieux" set "SILENCIEUX=1"
py -3.14 "%~dp0moteur\gerer-serveur.py" demarrer %*
set "RESULTAT=%ERRORLEVEL%"
echo.
if not defined SILENCIEUX pause
exit /b %RESULTAT%
