@echo off
setlocal
cd /d "%~dp0"
rem Lance la Tri-Sentinelle (surveillance des mails, messages et comptages).
rem Le processus signale EVENEMENT puis termine pour reveiller le Leader.
set "SILENCIEUX="
for %%A in (%*) do if /I "%%~A"=="--silencieux" set "SILENCIEUX=1"
py -3.14 -B -X utf8 "%~dp0moteur\superviser-sentinelle.py" %*
set "RESULTAT=%ERRORLEVEL%"
echo.
if not defined SILENCIEUX pause
exit /b %RESULTAT%
